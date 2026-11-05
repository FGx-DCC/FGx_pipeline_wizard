"""Unit tests for the run script writer."""

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from pipeline_wizard.dag import Dag
from pipeline_wizard.run_builder import RunBuilder
from pipeline_wizard.types import AbsolutePath

PIPELINE = """
name = "Demo"
description = "demo pipeline"
executor = "slurm"
[steps.a]
path = "a.sh"
description = "first"
[steps.b]
path = "b.sh"
after = ["a"]
[steps.c]
path = "c.sh"
after = ["a", "b"]
"""


def _build(dag: Dag, tmp_path: Path, *, skip_steps: int = 0) -> list[str]:
    builder = RunBuilder(
        AbsolutePath(tmp_path),
        AbsolutePath(tmp_path) / "config.sh",
        dag,
        starting_step=skip_steps + 1,
    )
    for step in dag.steps[skip_steps:]:
        builder.add_pipeline_step(step)
    out = tmp_path / "run.sh"
    builder.write_run_script(out)
    # Submit commands span several lines (shell continuations); put each on
    # one line so tests don't depend on layout. This is still quite fragile
    # and will break if there are any changes to how commands are written.
    flattened = re.sub(r"\\\n\s*", "", out.read_text())
    return [re.sub(r"[ \t]+", " ", line) for line in flattened.splitlines()]


def test_first_step_has_no_dependency(
    make_dag: Callable[..., Dag], tmp_path: Path
) -> None:
    """Should not add a dependency to scripts with no prerequisites.

    Given:
        A pipeline whose first script has no `after`.
    When:
        The run script is written.
    Then:
        Its sbatch line has no `--dependency`.

    """
    lines = _build(make_dag(PIPELINE), tmp_path)
    first = next(line for line in lines if "a.sh" in line and "sbatch" in line)

    assert "--dependency" not in first


def test_later_steps_depend_on_prerequisites(
    make_dag: Callable[..., Dag], tmp_path: Path
) -> None:
    """Should make scripts wait for the jobs they come after.

    Given:
        Script c that comes after a and b.
    When:
        The run script is written.
    Then:
        Its sbatch line has an afterok dependency referencing two jobs.

    """
    lines = _build(make_dag(PIPELINE), tmp_path)
    last = next(line for line in lines if "c.sh" in line and "sbatch" in line)

    assert "--dependency=afterok:" in last
    assert last.count("${jobid_") == 2


def test_write_fails_for_unwritable_path(
    make_dag: Callable[..., Dag], tmp_path: Path
) -> None:
    """Should raise OSError when the script can't be written.

    Given:
        An output path inside a missing directory.
    When:
        The run script is written.
    Then:
        An OSError is raised.

    """
    builder = RunBuilder(
        AbsolutePath(tmp_path),
        AbsolutePath(tmp_path) / "c.sh",
        make_dag(PIPELINE),
        0,
    )

    with pytest.raises(OSError):  # noqa: PT011
        builder.write_run_script(tmp_path / "missing" / "run.sh")


def test_local_executor_runs_scripts_directly(
    make_dag: Callable[..., Dag], tmp_path: Path
) -> None:
    """Should call scripts directly when the pipeline uses the local executor.

    Given:
        A pipeline with `executor = "local"`.
    When:
        The run script is written.
    Then:
        Scripts are invoked by path with no scheduler command.

    """
    dag = make_dag(PIPELINE.replace('"slurm"', '"local"'))

    text = "\n".join(_build(dag, tmp_path))

    assert f"{tmp_path / 'a.sh'}" in text
    assert "sbatch" not in text
    assert "qsub" not in text


def test_missing_executor_falls_back_to_local(
    make_dag: Callable[..., Dag], tmp_path: Path
) -> None:
    """Should fall back to running scripts directly with no executor.

    Given:
        A pipeline that doesn't specify an executor.
    When:
        The run script is written.
    Then:
        No scheduler command is used.

    """
    dag = make_dag(PIPELINE.replace('executor = "slurm"\n', ""))

    text = "\n".join(_build(dag, tmp_path))

    assert "sbatch" not in text
    assert "qsub" not in text


def test_pbs_executor_uses_qsub(
    make_dag: Callable[..., Dag], tmp_path: Path
) -> None:
    """Should submit scripts with qsub for a PBS pipeline.

    Given:
        A pipeline with `executor = "pbs"`.
    When:
        The run script is written.
    Then:
        Each script is submitted with qsub and dependencies use afterok.

    """
    dag = make_dag(PIPELINE.replace('"slurm"', '"pbs"'))

    lines = _build(dag, tmp_path)
    last = next(line for line in lines if "c.sh" in line and "qsub" in line)

    assert "-W depend=afterok:" in last


def test_script_directives_are_passed_to_scheduler(
    make_dag: Callable[..., Dag], tmp_path: Path
) -> None:
    """Should translate script header directives into submit options.

    Given:
        A slurm pipeline whose script has an `#SBATCH --mem` header line.
    When:
        The run script is written.
    Then:
        The script's submit line includes that option.

    """
    (tmp_path / "a.sh").write_text("#!/bin/bash\n#SBATCH --mem=4G\n")

    lines = _build(make_dag(PIPELINE), tmp_path)
    first = next(line for line in lines if "a.sh" in line and "sbatch" in line)

    assert "--mem=4G" in first


def test_dependencies_are_only_on_earlier_jobs_when_resuming(
    make_dag: Callable[..., Dag], tmp_path: Path
) -> None:
    """Should not depend on jobs that were skipped.

    Given:
        A run that skips the first step.
    When:
        The run script is written.
    Then:
        No submit line references a job id that was never submitted.

    """
    lines = _build(make_dag(PIPELINE), tmp_path, skip_steps=1)
    submitted = [line for line in lines if "sbatch" in line]

    assert submitted
    assert "jobid_1_1" not in "\n".join(submitted)
