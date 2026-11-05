"""Unit tests for the job executors."""

import re

import pytest

from pipeline_wizard.directives import (
    Directives,
    EventNotification,
    Memory,
    WallTime,
)
from pipeline_wizard.executors import (
    LocalExecutor,
    PBSExecutor,
    SlurmExecutor,
    get_available_system_executors,
)
from pipeline_wizard.types import AbsolutePath

SCRIPT = AbsolutePath("/scripts/a.sh")


def _flat(command: str) -> str:
    """Collapse shell line continuations so layout doesn't matter.

    This is quite fragile and may break upon implementation changes (in how
    lines are written).

    """
    return re.sub(r"\s+", " ", command.replace("\\\n", " ")).strip()


def test_executor_names() -> None:
    """Should name each executor.

    Given:
        One of each executor.
    When:
        Their names are requested.
    Then:
        Each name is distinct and non-empty.

    """
    names = {
        e.executor_name()
        for e in (SlurmExecutor(), PBSExecutor(), LocalExecutor())
    }

    assert len(names) == 3
    assert "" not in names


def test_executors_equal_by_type() -> None:
    """Should treat executors of the same kind as equal.

    Given:
        Two instances of the same executor and one of another.
    When:
        They are compared.
    Then:
        Same kinds are equal and different kinds (or non-executors) are not.

    """
    assert SlurmExecutor() == SlurmExecutor()
    assert SlurmExecutor() != PBSExecutor()
    assert SlurmExecutor() != "slurm"


def test_slurm_submit_basic() -> None:
    """Should submit with sbatch and capture the parsable job id.

    Given:
        A script and empty directives.
    When:
        The slurm submit text is requested.
    Then:
        It assigns the job id to the variable using sbatch --parsable,
        --export=ALL is always added.

    """
    text = _flat(
        SlurmExecutor().submit_text(SCRIPT, "jobid_1_1", Directives(), None)
    )

    assert text.startswith("jobid_1_1=$( sbatch --parsable ")
    assert str(SCRIPT) in text
    assert "--export=ALL" in text
    assert "--dependency" not in text


def test_slurm_submit_with_dependencies_and_directives() -> None:
    """Should add dependency and directive options for slurm.

    Given:
        Dependent jobs and several directives.
    When:
        The slurm submit text is requested.
    Then:
        The dependency and each set directive appear as options.

    """
    directives = Directives(
        job_name="my job",
        cpus_per_task="4",
        memory=Memory.parse("8G"),
        wall_time=WallTime(hours=2),
        event_notification=EventNotification.END,
    )

    text = SlurmExecutor().submit_text(
        SCRIPT, "jobid", directives, ['"${a}"', '"${b}"']
    )

    assert '--dependency=afterok:"${a}":"${b}"' in text
    assert "--job-name='my job'" in text
    assert "--cpus-per-task=4" in text
    assert "--mem=8G" in text
    assert "--time=0-2:0:0" in text
    assert "--mail-type=END" in text
    assert "--export=ALL" in text


def test_slurm_submit_skips_unset_directives() -> None:
    """Should not emit options for unset directives.

    Given:
        Directives with only a job name.
    When:
        The slurm submit text is requested.
    Then:
        No other directive flags are present.

    """
    text = SlurmExecutor().submit_text(
        SCRIPT, "j", Directives(job_name="x"), None
    )

    assert "--job-name=x" in text
    assert "--mem" not in text
    assert "--time" not in text


def test_slurm_submit_quotes_values() -> None:
    """Should shell quote directive values.

    Given:
        A log file path containing a shell metacharacter.
    When:
        The slurm submit text is requested.
    Then:
        The value is quoted.

    """
    text = SlurmExecutor().submit_text(
        SCRIPT, "j", Directives(log_file="a; rm -rf /"), None
    )

    assert "--output='a; rm -rf /'" in text


def test_slurm_requires_directives() -> None:
    """Should refuse to submit without directives.

    Given:
        No directives.
    When:
        The slurm submit text is requested.
    Then:
        A ValueError is raised.

    """
    with pytest.raises(ValueError, match="Directives required"):
        SlurmExecutor().submit_text(SCRIPT, "j", None, None)


def test_pbs_requires_directives() -> None:
    """Should refuse to submit without directives.

    Given:
        No directives.
    When:
        The PBS submit text is requested.
    Then:
        A ValueError is raised.

    """
    with pytest.raises(ValueError, match="Directives required"):
        PBSExecutor().submit_text(SCRIPT, "j", None, None)


def test_pbs_submit_basic() -> None:
    """Should submit with qsub and capture the job id.

    Given:
        A script and empty directives.
    When:
        The PBS submit text is requested.
    Then:
        It assigns the qsub output to the variable,
        -V flag is always added

    """
    text = _flat(
        PBSExecutor().submit_text(SCRIPT, "jobid", Directives(), None)
    )

    assert text.startswith("jobid=$( qsub")
    assert str(SCRIPT) in text
    assert "-V" in text
    assert "depend" not in text


def test_pbs_submit_with_dependencies_and_directives() -> None:
    """Should add dependency and directive options for PBS.

    Given:
        Dependent jobs and several directives.
    When:
        The PBS submit text is requested.
    Then:
        Options use PBS flags and resources are in -l options.

    """
    directives = Directives(
        job_name="job",
        wall_time=WallTime(hours=2),
        event_notification=EventNotification.BEGIN,
    )

    text = _flat(PBSExecutor().submit_text(SCRIPT, "j", directives, ["${a}"]))

    assert "-W depend=afterok:${a}" in text
    assert "-N job" in text
    assert "-m b" in text
    assert " -V" in text
    assert "-l walltime=2:0:0" in text


@pytest.mark.parametrize(
    ("directives", "expected"),
    [
        (
            Directives(cpus_per_task="4"),
            "-l select=1:ncpus=4:mpiprocs=1:ompthreads=4",
        ),
        (Directives(task_count="4"), "-l select=1:ncpus=4:mpiprocs=4"),
        (
            Directives(cpus_per_task="2", task_count="3"),
            "-l select=1:ncpus=6:mpiprocs=3:ompthreads=2",
        ),
        (
            Directives(memory=Memory.parse("8G")),
            "-l select=1:ncpus=1:mpiprocs=1:mem=8gb",
        ),
    ],
)
def test_pbs_submit_resources(directives: Directives, expected: str) -> None:
    """Should build a PBS select statement from resource directives.

    Given:
        CPU, task and/or memory directives.
    When:
        The PBS submit text is requested.
    Then:
        A matching `-l select=...` option is present.

    """
    text = PBSExecutor().submit_text(SCRIPT, "j", directives, None)

    assert expected in text


def test_pbs_submit_without_resources_has_no_select() -> None:
    """Should not emit a select statement when no resources are requested.

    Given:
        Directives with only a job name.
    When:
        The PBS submit text is requested.
    Then:
        There is no `select=`.

    """
    text = PBSExecutor().submit_text(
        SCRIPT, "j", Directives(job_name="x"), None
    )

    assert "select=" not in text


def test_local_submit_runs_script_directly() -> None:
    """Should just run the script locally.

    Given:
        A script (with or without directives).
    When:
        The local submit text is requested.
    Then:
        The text is the script path.

    """
    executor = LocalExecutor()

    assert executor.submit_text(SCRIPT, "j", None, None) == str(SCRIPT)
    assert executor.submit_text(SCRIPT, "j", Directives(), ["a"]) == str(
        SCRIPT
    )


@pytest.mark.parametrize(
    ("available", "expected"),
    [
        ([], [LocalExecutor()]),
        (["sbatch"], [LocalExecutor(), SlurmExecutor()]),
        (["qsub"], [LocalExecutor(), PBSExecutor()]),
        (
            ["sbatch", "qsub"],
            [LocalExecutor(), SlurmExecutor(), PBSExecutor()],
        ),
    ],
)
def test_available_executors(
    monkeypatch: pytest.MonkeyPatch,
    available: list[str],
    expected: list[object],
) -> None:
    """Should only offer executors whose commands exist.

    Given:
        A system with some of sbatch and qsub on the path.
    When:
        The available executors are requested.
    Then:
        Local is always present, with slurm/PBS only when installed.

    """
    monkeypatch.setattr(
        "shutil.which",
        lambda cmd: f"/usr/bin/{cmd}" if cmd in available else None,
    )

    assert get_available_system_executors() == expected
