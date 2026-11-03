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
