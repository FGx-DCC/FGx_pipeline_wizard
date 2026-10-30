"""Unit tests for the run script writer."""

from collections.abc import Callable
from pathlib import Path

import pytest

from pipeline_wizard.dag import Dag
from pipeline_wizard.run_builder import RunBuilder

PIPELINE = """
name = "Demo"
description = "demo pipeline"
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
        tmp_path, tmp_path / "config.sh", dag, starting_step=skip_steps + 1
    )
    for step in dag.steps[skip_steps:]:
        builder.add_pipeline_step(step)
    out = tmp_path / "run.sh"
    builder.write_run_script(out)
    return out.read_text().splitlines()


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
    builder = RunBuilder(tmp_path, tmp_path / "c.sh", make_dag(PIPELINE), 0)

    with pytest.raises(OSError):  # noqa: PT011
        builder.write_run_script(tmp_path / "missing" / "run.sh")
