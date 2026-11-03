"""Classes describing the data associated with a pipeline script."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import Flag, auto
from pathlib import Path
from typing import ClassVar

from pipeline_wizard.exceptions import (
    NotUpperError,
)


@dataclass
class Parameter:
    """Represents a configuration parameter (such as a file path)."""

    name: str
    """The name of the parameter (to put into the config file).

    This must be capitalised.

    """

    default: str | int | bool | list[str] | list[int]
    """The default value used for the parameter."""

    def __post_init__(self) -> None:
        """Raise if name is not upper case."""
        if self.name != self.name.upper():
            raise NotUpperError(self.name)


@dataclass
class Requirement:
    """Represents an external requirement for the pipeline (a reference)."""

    name: str
    """The name of the requirement (to put into the config file).

    This must be capitalised.

    """

    instructions: str
    """Instructions or a URL on how to get said requirement.

    If this is a valid URL and the user doesn't have the file, the file will
    be retrieved via said URL.

    """

    def __post_init__(self) -> None:
        """Raise if name is not upper case."""
        if self.name != self.name.upper():
            raise NotUpperError(self.name)


class EventNotification(Flag):
    """Scheduler agnostic job events to send notifications for."""

    NONE = 0
    BEGIN = auto()
    END = auto()
    FAIL = auto()
    ALL = BEGIN | END | FAIL

    def as_slurm(self) -> str:
        """Return as a slurm --mail-type value."""
        if not self:
            return "NONE"
        if self == EventNotification.ALL:
            return "ALL"
        return ",".join(
            event.name
            for event in (self.BEGIN, self.END, self.FAIL)
            if event in self and event.name is not None
        )

    def as_pbs(self) -> str:
        """Return as a PBS -m value (a=abort, b=begin, e=end)."""
        if not self:
            return "n"
        letters = {
            EventNotification.BEGIN: "b",
            EventNotification.END: "e",
            EventNotification.FAIL: "a",
        }
        return "".join(
            letter for event, letter in letters.items() if event in self
        )


@dataclass(frozen=True)
class CopyEnvironment:
    """Which environment variables to copy into the job.

    `variables=None` is the sentinel for "everything" use
    `CopyEnvironment.ALL`. An empty tuple means copy nothing.

    """

    variables: tuple[str, ...] | None = None

    ALL: ClassVar[CopyEnvironment]

    def as_slurm(self) -> str:
        """Return as a slurm --export value."""
        if self.variables is None:
            return "ALL"
        return ",".join(self.variables) or "NONE"

    @property
    def pbs_flag(self) -> str:
        """PBS uses a (-V) for all vs. specific (-v) variables."""
        return "-V" if self.variables is None else "-v"

    def as_pbs(self) -> str:
        """Return as a PBS value ("" means a bare -V flag)."""
        return "" if self.variables is None else ",".join(self.variables)


CopyEnvironment.ALL = CopyEnvironment()


@dataclass
class Directives:
    """Represents scheduler agnostic directives for a given script.

    These are most useful for scripts that are to be executed by some job
    scheduler (such as slurm or pbs).

    All data members are nullable as none are an actual requirement (local
    scripts not meant to be submitted to a scheduler have no need for any of
    these).

    """

    account: str | None = field(
        default=None,
        metadata={"slurm": "--account", "pbs": "-A"},
    )
    array: str | None = field(
        default=None,
        metadata={"slurm": "--array", "pbs": "-J"},
    )
    copy_environment: CopyEnvironment | None = field(
        default=None,
        metadata={"slurm": "--export", "pbs": "-V"},
    )
    cpus_per_task: str | None = field(
        default=None,
        metadata={"slurm": "--cpus-per-task", "pbs": "-l select"},
    )
    error_file: str | None = field(
        default=None,
        metadata={"slurm": "--error", "pbs": "-e"},
    )
    event_notification: EventNotification | None = field(
        default=None,
        metadata={"slurm": "--mail-type", "pbs": "-m"},
    )
    job_name: str | None = field(
        default=None,
        metadata={"slurm": "--job-name", "pbs": "-N"},
    )
    log_file: str | None = field(
        default=None,
        metadata={"slurm": "--output", "pbs": "-o"},
    )
    memory: str | None = field(
        default=None,
        metadata={"slurm": "--mem", "pbs": "-l select"},
    )
    partition: str | None = field(
        default=None,
        metadata={"slurm": "--partition", "pbs": "-q"},
    )
    qos: str | None = field(
        default=None,
        metadata={"slurm": "--qos", "pbs": "-l qos"},
    )
    task_count: str | None = field(
        default=None,
        metadata={"slurm": "--ntasks", "pbs": "-l select"},
    )
    wall_time: str | None = field(
        default=None,
        metadata={"slurm": "--time", "pbs": "-l walltime"},
    )

    def _render(self, value: object, scheduler: str) -> str | None:
        """Convert a directive value to its scheduler specific string."""
        if value is None:
            return None
        if isinstance(value, (EventNotification, CopyEnvironment)):
            return getattr(value, f"as_{scheduler}")()
        return str(value)

    def as_slurm(self) -> dict[str, str | None]:
        """Return directives as used in slurm."""
        return {
            field.metadata["slurm"]: self._render(
                getattr(self, field.name), "slurm"
            )
            for field in fields(self)
        }

    def as_pbs(self) -> dict[str, str | None]:
        """Return directives as used in PBS."""
        result: dict[str, str | None] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            key = f.metadata["pbs"]
            if isinstance(value, CopyEnvironment):
                key = value.pbs_flag
            result[key] = self._render(value, "pbs")
        return result


@dataclass
class Script:
    """Represents a script with associated information."""

    name: str
    """Name of script."""

    path: Path
    """Absolute path to the script."""

    description: str
    """What the script attempts to do."""

    dependencies: list[Script] = field(default_factory=list)
    """Scripts required to be completed for this to run."""

    parameters: dict[str, Parameter] = field(default_factory=dict)
    """Configuration parameters needed."""

    requires: dict[str, Requirement] = field(default_factory=dict)
    """File dependencies (for example, a reference genome)."""

    directives: Directives | None = field(default=None)
    """The job scheduler directives for the script (if any)."""
