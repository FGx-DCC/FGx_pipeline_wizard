"""Unit tests for reading scheduler directives from script headers."""

from pathlib import Path

import pytest

from pipeline_wizard.directive_parser import read_directives
from pipeline_wizard.directives import (
    CopyEnvironment,
    EventNotification,
    Memory,
    WallTime,
)
from pipeline_wizard.types import AbsolutePath


def _read(tmp_path: Path, text: str):  # noqa: ANN202
    script = tmp_path / "script.sh"
    script.write_text(text)
    return read_directives(AbsolutePath(script))


def test_script_without_directives(tmp_path: Path) -> None:
    """Should return empty directives for a plain script.

    Given:
        A script with no #SBATCH or #PBS lines.
    When:
        Its directives are read.
    Then:
        Every directive is unset.

    """
    directives = _read(tmp_path, "#!/bin/bash\necho hi\n")

    assert set(directives.as_slurm().values()) == {None}


def test_reads_long_slurm_options(tmp_path: Path) -> None:
    """Should read long form slurm options.

    Given:
        A script with `--flag=value` and `--flag value` #SBATCH lines.
    When:
        Its directives are read.
    Then:
        The values are present on the Directives.

    """
    directives = _read(
        tmp_path,
        "#!/bin/bash\n"
        "#SBATCH --job-name=job\n"
        "#SBATCH --cpus-per-task 4\n"
        "#SBATCH --ntasks=2\n"
        "#SBATCH --mem=8G\n"
        "#SBATCH --time=01:30:00\n"
        "#SBATCH --output=out.log\n"
        "#SBATCH --error=err.log\n"
        "#SBATCH --array=1-10%2\n",
    )

    assert directives.job_name == "job"
    assert directives.cpus_per_task == "4"
    assert directives.task_count == "2"
    assert directives.memory == Memory.parse("8G")
    assert directives.wall_time == WallTime(hours=1, minutes=30)
    assert directives.log_file == "out.log"
    assert directives.error_file == "err.log"
    assert directives.array == "1-10%2"


def test_reads_short_slurm_options(tmp_path: Path) -> None:
    """Should read short form slurm options.

    Given:
        A script using -J, -c, -n, -t, -o, -e and -a.
    When:
        Its directives are read.
    Then:
        They map to the same directives as the long forms.

    """
    directives = _read(
        tmp_path,
        "#SBATCH -J job -c 2\n"
        "#SBATCH -n3\n"
        "#SBATCH -t 10\n"
        "#SBATCH -o o.log -e e.log\n"
        "#SBATCH -a 1-4\n",
    )

    assert directives.job_name == "job"
    assert directives.cpus_per_task == "2"
    assert directives.task_count == "3"
    assert directives.wall_time == WallTime(minutes=10)
    assert directives.log_file == "o.log"
    assert directives.error_file == "e.log"
    assert directives.array == "1-4"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("30", WallTime(minutes=30)),
        ("5:30", WallTime(minutes=5, seconds=30)),
        ("1:02:03", WallTime(hours=1, minutes=2, seconds=3)),
        ("2-3:04:05", WallTime(days=2, hours=3, minutes=4, seconds=5)),
    ],
)
def test_reads_slurm_wall_times(
    tmp_path: Path, text: str, expected: WallTime
) -> None:
    """Should understand slurm time formats.

    Given:
        A script with a #SBATCH --time in a given format.
    When:
        Its directives are read.
    Then:
        The wall time matches.

    """
    directives = _read(tmp_path, f"#SBATCH --time={text}\n")

    assert directives.wall_time == expected


@pytest.mark.xfail(
    reason="Slurm D-H and D-H:M wall times are rejected (zip length check)",
    strict=True,
)
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1-12", WallTime(days=1, hours=12)),
        ("1-12:30", WallTime(days=1, hours=12, minutes=30)),
    ],
)
def test_reads_partial_slurm_day_wall_times(
    tmp_path: Path, text: str, expected: WallTime
) -> None:
    """Should understand the D-H and D-H:M slurm time formats.

    Given:
        A script with a #SBATCH --time like `1-12` (valid in slurm).
    When:
        Its directives are read.
    Then:
        The wall time matches.

    """
    directives = _read(tmp_path, f"#SBATCH --time={text}\n")

    assert directives.wall_time == expected


@pytest.mark.parametrize("text", ["abc", "1:2:3:4", "1-1:2:3:4"])
def test_invalid_slurm_wall_time_raises(tmp_path: Path, text: str) -> None:
    """Should raise on slurm times it can't parse.

    Given:
        A script with a malformed --time.
    When:
        Its directives are read.
    Then:
        A ValueError is raised.

    """
    with pytest.raises(ValueError):  # noqa: PT011
        _read(tmp_path, f"#SBATCH --time={text}\n")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("BEGIN", EventNotification.BEGIN),
        ("END,FAIL", EventNotification.END | EventNotification.FAIL),
        ("ALL", EventNotification.ALL),
        ("NONE", EventNotification.NONE),
        ("end", EventNotification.END),
        ("REQUEUE,END", EventNotification.END),
    ],
)
def test_reads_slurm_mail_types(
    tmp_path: Path, text: str, expected: EventNotification
) -> None:
    """Should map slurm mail types to notification events.

    Given:
        A script with `--mail-type`, possibly with unsupported types.
    When:
        Its directives are read.
    Then:
        The supported events are set and others are ignored.

    """
    directives = _read(tmp_path, f"#SBATCH --mail-type={text}\n")

    assert directives.event_notification == expected


def test_slurm_mail_types_merge_across_lines(tmp_path: Path) -> None:
    """Should combine notifications from several lines.

    Given:
        Two #SBATCH --mail-type lines.
    When:
        Its directives are read.
    Then:
        The events are merged.

    """
    directives = _read(
        tmp_path,
        "#SBATCH --mail-type=BEGIN\n#SBATCH --mail-type=END\n",
    )

    assert (
        directives.event_notification
        == EventNotification.BEGIN | EventNotification.END
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ALL", CopyEnvironment.ALL),
        ("ALL,FOO=bar", CopyEnvironment.ALL),
        ("NONE", CopyEnvironment(())),
        ("A,B", CopyEnvironment(("A", "B"))),
    ],
)
def test_reads_slurm_export(
    tmp_path: Path, text: str, expected: CopyEnvironment
) -> None:
    """Should map --export to CopyEnvironment.

    Given:
        A script with an --export value.
    When:
        Its directives are read.
    Then:
        The copy_environment matches.

    """
    directives = _read(tmp_path, f"#SBATCH --export={text}\n")

    assert directives.copy_environment == expected


def test_later_lines_override_earlier(tmp_path: Path) -> None:
    """Should use the last value given for a directive.

    Given:
        Two #SBATCH --job-name lines.
    When:
        Its directives are read.
    Then:
        The later name is used.

    """
    directives = _read(
        tmp_path, "#SBATCH --job-name=a\n#SBATCH --job-name=b\n"
    )

    assert directives.job_name == "b"


def test_ignores_comments_and_unknown_options(tmp_path: Path) -> None:
    """Should ignore trailing comments and options it doesn't model.

    Given:
        A #SBATCH line with a trailing comment and an unknown flag.
    When:
        Its directives are read.
    Then:
        Only the known option is read.

    """
    directives = _read(
        tmp_path,
        "#SBATCH --exclusive --job-name=job # a comment\n"
        "#SBATCH --partition=main\n",
    )

    assert directives.job_name == "job"


def test_stops_reading_at_first_command(tmp_path: Path) -> None:
    """Should only read the header block, as the schedulers do.

    Given:
        A #SBATCH line placed after the first command.
    When:
        Its directives are read.
    Then:
        It is ignored, but blank lines in the header are fine.

    """
    directives = _read(
        tmp_path,
        "#!/bin/bash\n\n#SBATCH --job-name=yes\necho hi\n#SBATCH --mem=4G\n",
    )

    assert directives.job_name == "yes"
    assert directives.memory is None


def test_option_missing_value_raises(tmp_path: Path) -> None:
    """Should raise when a flag that needs a value has none.

    Given:
        A `#SBATCH --job-name` line with no value.
    When:
        Its directives are read.
    Then:
        A ValueError is raised.

    """
    with pytest.raises(ValueError, match="missing a value"):
        _read(tmp_path, "#SBATCH --job-name\n")


def test_reads_pbs_options(tmp_path: Path) -> None:
    """Should read common PBS options.

    Given:
        A script with -N, -o, -e, -J and -m #PBS lines.
    When:
        Its directives are read.
    Then:
        The values are present.

    """
    directives = _read(
        tmp_path,
        "#PBS -N job\n#PBS -o o.log\n#PBS -e e.log\n#PBS -J 1-4\n#PBS -m be\n",
    )

    assert directives.job_name == "job"
    assert directives.log_file == "o.log"
    assert directives.error_file == "e.log"
    assert directives.array == "1-4"
    assert directives.event_notification == (
        EventNotification.BEGIN | EventNotification.END
    )


def test_reads_pbs_resources(tmp_path: Path) -> None:
    """Should read PBS -l resources.

    Given:
        PBS `-l walltime` and `-l mem` lines.
    When:
        Its directives are read.
    Then:
        The wall time and memory are set.

    """
    directives = _read(
        tmp_path, "#PBS -l walltime=2:30:00\n#PBS -l mem=4gb,ncpus=8\n"
    )

    assert directives.wall_time == WallTime(hours=2, minutes=30)
    assert directives.memory == Memory.parse("4G")
    assert directives.cpus_per_task == "8"


def test_reads_pbs_select(tmp_path: Path) -> None:
    """Should read a simple PBS select statement.

    Given:
        `-l select=1:ncpus=4:mpiprocs=2:mem=8gb`.
    When:
        Its directives are read.
    Then:
        CPUs, tasks and memory are set.

    """
    directives = _read(
        tmp_path, "#PBS -l select=1:ncpus=4:mpiprocs=2:mem=8gb\n"
    )

    assert directives.memory == Memory.parse("8G")
    assert directives.task_count == "2"


def test_reads_pbs_environment(tmp_path: Path) -> None:
    """Should read PBS environment options.

    Given:
        A script with `-V` or `-v A,B`.
    When:
        Its directives are read.
    Then:
        -V copies everything and -v copies the named variables.

    """
    assert _read(tmp_path, "#PBS -V\n").copy_environment == CopyEnvironment.ALL
    assert _read(tmp_path, "#PBS -v A,B\n").copy_environment == (
        CopyEnvironment(("A", "B"))
    )


@pytest.mark.parametrize("text", ["1-10:10:10", "1:2:3:4"])
def test_invalid_pbs_wall_time_raises(tmp_path: Path, text: str) -> None:
    """Should raise on PBS walltimes it can't parse.

    Given:
        A PBS script with a malformed walltime.
    When:
        Its directives are read.
    Then:
        A ValueError is raised.

    """
    with pytest.raises(ValueError):  # noqa: PT011
        _read(tmp_path, f"#PBS -l walltime={text}\n")


@pytest.mark.xfail(
    reason="ncpus in a PBS select is the total, but is read as cpus_per_task",
    strict=True,
)
def test_pbs_select_round_trips_cpus_per_task(tmp_path: Path) -> None:
    """Should read cpus per task from ompthreads in a PBS select.

    Given:
        `select=1:ncpus=8:mpiprocs=4:ompthreads=2` (4 tasks x 2 cpus).
    When:
        Its directives are read.
    Then:
        There are 2 cpus per task and 4 tasks.

    """
    directives = _read(
        tmp_path, "#PBS -l select=1:ncpus=8:mpiprocs=4:ompthreads=2\n"
    )

    assert directives.cpus_per_task == "2"
    assert directives.task_count == "4"


@pytest.mark.xfail(
    reason="--mem=0 (all node memory) is valid in slurm but raises",
    strict=True,
)
def test_slurm_mem_zero_is_accepted(tmp_path: Path) -> None:
    """Should not fail on slurm's `--mem=0`.

    Given:
        A script with `#SBATCH --mem=0`.
    When:
        Its directives are read.
    Then:
        No error is raised.

    """
    _read(tmp_path, "#SBATCH --mem=0\n")
