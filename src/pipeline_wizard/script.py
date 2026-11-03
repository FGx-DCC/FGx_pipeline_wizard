"""Classes describing the data associated with a pipeline script."""

from __future__ import annotations

from dataclasses import dataclass, field
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

    account: str | None
    array: str | None
    copy_environment: str | None
    cpus_per_task: str | None
    error_file: str | None
    event_notification: str | None
    job_name: str | None
    log_file: str | None
    memory: str | None
    partition: str | None
    qos: str | None
    task_count: str | None
    wall_time: str | None
    work_directory: str | None


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
