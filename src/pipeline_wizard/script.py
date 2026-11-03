"""Classes describing the data associated with a pipeline script."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path

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
        metadata={"slurm": "--account"},
    )
    array: str | None = field(
        default=None,
        metadata={"slurm": "--array"},
    )
    copy_environment: str | None = field(
        default=None,
        metadata={"slurm": "--export"},
    )
    cpus_per_task: str | None = field(
        default=None,
        metadata={"slurm": "cpus-per-task"},
    )
    error_file: str | None = field(
        default=None,
        metadata={"slurm": "--error"},
    )
    event_notification: str | None = field(
        default=None,
        metadata={"slurm": "--mail"},
    )
    job_name: str | None = field(
        default=None,
        metadata={"slurm": "--job-name"},
    )
    log_file: str | None = field(
        default=None,
        metadata={"slurm": "--output"},
    )
    memory: str | None = field(
        default=None,
        metadata={"slurm": "--mem"},
    )
    partition: str | None = field(
        default=None,
        metadata={"slurm": "--partition"},
    )
    qos: str | None = field(
        default=None,
        metadata={"slurm": "--qos"},
    )
    task_count: str | None = field(
        default=None,
        metadata={"slurm": "--ntasks"},
    )
    wall_time: str | None = field(
        default=None,
        metadata={"slurm": "--time"},
    )

    def as_slurm(self) -> dict[str, str | None]:
        """Return directives as used in slurm."""
        return {
            field.metadata["slurm"]: getattr(self, field.name)
            for field in fields(self)
        }


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
