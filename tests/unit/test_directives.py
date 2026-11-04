"""Unit tests for the scheduler agnostic directive classes."""

from datetime import timedelta

import pytest

from pipeline_wizard.directives import (
    CopyEnvironment,
    Directives,
    EventNotification,
    Memory,
    WallTime,
)


@pytest.mark.parametrize(
    ("seconds", "slurm", "pbs"),
    [
        (90, "0-0:1:30", "0:1:30"),
        (3600, "0-1:0:0", "1:0:0"),
        (86400 + 3661, "1-1:1:1", "25:1:1"),
    ],
)
def test_wall_time_formats(seconds: int, slurm: str, pbs: str) -> None:
    """Should format wall times for each scheduler.

    Given:
        A wall time (possibly longer than a day).
    When:
        It is converted for slurm and PBS.
    Then:
        Slurm gets D-H:M:S and PBS gets total hours H:M:S.

    """
    wall_time = WallTime(seconds=seconds)

    assert wall_time.as_slurm() == slurm
    assert wall_time.as_pbs() == pbs


def test_wall_time_is_a_timedelta() -> None:
    """Should compare equal to the equivalent timedelta.

    Given:
        A WallTime and a timedelta of the same length.
    When:
        They are compared.
    Then:
        They are equal.

    """
    assert WallTime(hours=2) == timedelta(hours=2)


@pytest.mark.parametrize(
    ("event", "slurm", "pbs"),
    [
        (EventNotification.NONE, "NONE", "n"),
        (EventNotification.ALL, "ALL", "bea"),
        (EventNotification.BEGIN, "BEGIN", "b"),
        (EventNotification.END | EventNotification.FAIL, "END,FAIL", "ea"),
    ],
)
def test_event_notification_formats(
    event: EventNotification, slurm: str, pbs: str
) -> None:
    """Should translate notification events for each scheduler.

    Given:
        A set of notification events.
    When:
        It is converted for slurm and PBS.
    Then:
        The scheduler specific values are returned.

    """
    assert event.as_slurm() == slurm
    assert event.as_pbs() == pbs


def test_copy_environment_all() -> None:
    """Should copy the whole environment with the ALL sentinel.

    Given:
        CopyEnvironment.ALL.
    When:
        It is converted for slurm and PBS.
    Then:
        Slurm exports ALL and PBS uses a bare -V flag.

    """
    assert CopyEnvironment.ALL.as_slurm() == "ALL"
    assert CopyEnvironment.ALL.pbs_flag == "-V"
    assert CopyEnvironment.ALL.as_pbs() == ""


def test_copy_environment_named_variables() -> None:
    """Should copy only the named variables.

    Given:
        A CopyEnvironment naming two variables.
    When:
        It is converted for slurm and PBS.
    Then:
        Both schedulers get a comma separated list (PBS with -v).

    """
    env = CopyEnvironment(("A", "B"))

    assert env.as_slurm() == "A,B"
    assert env.pbs_flag == "-v"
    assert env.as_pbs() == "A,B"


def test_copy_environment_nothing_for_slurm() -> None:
    """Should export nothing when given no variables.

    Given:
        A CopyEnvironment with an empty tuple.
    When:
        It is converted for slurm.
    Then:
        The value is NONE.

    """
    assert CopyEnvironment(()).as_slurm() == "NONE"


@pytest.mark.parametrize(
    ("text", "size_bytes"),
    [
        ("8G", 8 * 2**30),
        ("8GB", 8 * 2**30),
        ("8gb", 8 * 2**30),
        ("500M", 500 * 2**20),
        ("1.5g", 3 * 2**29),
        ("2 T", 2 * 2**40),
        ("64K", 64 * 2**10),
        ("500", 500 * 2**20),
    ],
)
def test_memory_parse(text: str, size_bytes: int) -> None:
    """Should parse human readable memory values.

    Given:
        A memory string with (or without) a unit.
    When:
        It is parsed.
    Then:
        The size is in bytes, with bare numbers treated as megabytes.

    """
    assert Memory.parse(text) == Memory(size_bytes)


@pytest.mark.parametrize("text", ["", "abc", "8X", "-4G", "G8"])
def test_memory_parse_rejects_invalid(text: str) -> None:
    """Should reject values that aren't memory sizes.

    Given:
        An invalid memory string.
    When:
        It is parsed.
    Then:
        A ValueError is raised.

    """
    with pytest.raises(ValueError, match="Invalid memory"):
        Memory.parse(text)


@pytest.mark.parametrize("size", [0, -1])
def test_memory_must_be_positive(size: int) -> None:
    """Should not allow non-positive memory.

    Given:
        A zero or negative byte count.
    When:
        A Memory is created.
    Then:
        A ValueError is raised.

    """
    with pytest.raises(ValueError, match="positive"):
        Memory(size)


@pytest.mark.parametrize(
    ("text", "slurm", "pbs"),
    [
        ("8G", "8G", "8gb"),
        ("500M", "500M", "500mb"),
        ("2048M", "2G", "2gb"),
        ("2T", "2048G", "2tb"),
        ("64K", "1M", "64kb"),
        ("1536K", "2M", "1536kb"),
    ],
)
def test_memory_formats(text: str, slurm: str, pbs: str) -> None:
    """Should format memory for each scheduler.

    Given:
        A memory size.
    When:
        It is converted for slurm and PBS.
    Then:
        Slurm uses G or M (rounding up) and PBS uses the largest exact unit.

    """
    memory = Memory.parse(text)

    assert memory.as_slurm() == slurm
    assert memory.as_pbs() == pbs


def test_empty_directives_translate_to_none_values() -> None:
    """Should translate unset directives to None.

    Given:
        A Directives with nothing set.
    When:
        It is converted for slurm and PBS.
    Then:
        Every value is None.

    """
    directives = Directives()

    assert set(directives.as_slurm().values()) == {None}
    assert set(directives.as_pbs().values()) == {None}


def test_directives_slurm_translation() -> None:
    """Should translate directives to slurm flags.

    Given:
        A Directives with several values set.
    When:
        It is converted for slurm.
    Then:
        Each value is under its slurm flag.

    """
    directives = Directives(
        job_name="job",
        cpus_per_task="4",
        task_count="2",
        memory=Memory.parse("8G"),
        wall_time=WallTime(hours=1),
        event_notification=EventNotification.ALL,
        copy_environment=CopyEnvironment.ALL,
    )

    result = directives.as_slurm()

    assert result["--job-name"] == "job"
    assert result["--cpus-per-task"] == "4"
    assert result["--ntasks"] == "2"
    assert result["--mem"] == "8G"
    assert result["--time"] == "0-1:0:0"
    assert result["--mail-type"] == "ALL"
    assert result["--export"] == "ALL"


def test_directives_pbs_translation() -> None:
    """Should translate directives to PBS flags.

    Given:
        A Directives with several values set.
    When:
        It is converted for PBS.
    Then:
        Each value is under its PBS flag, and slurm only fields are omitted.

    """
    directives = Directives(
        job_name="job",
        cpus_per_task="4",
        memory=Memory.parse("8G"),
        wall_time=WallTime(hours=1),
        event_notification=EventNotification.BEGIN,
        copy_environment=CopyEnvironment(("A",)),
    )

    result = directives.as_pbs()

    assert result["-N"] == "job"
    assert result["-l walltime"] == "1:0:0"
    assert result["-m"] == "b"
    assert result["-v"] == "A"
    assert "--cpus-per-task" not in result
    assert "--mem" not in result


def test_directives_pbs_copy_all_uses_bare_flag() -> None:
    """Should use a bare -V for PBS when copying the whole environment.

    Given:
        A Directives that copies all of the environment.
    When:
        It is converted for PBS.
    Then:
        The flag is -V with an empty value.

    """
    result = Directives(copy_environment=CopyEnvironment.ALL).as_pbs()

    assert result["-V"] == ""
