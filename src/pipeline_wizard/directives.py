"""Translation layer for different job executor directives."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, fields
from enum import Flag, auto
from typing import ClassVar, Protocol, runtime_checkable

SKIP_DIRECTIVE = sentinel("SKIP_DIRECTIVE")


@runtime_checkable
class SchedulerValue(Protocol):
    """A value that can be converted for different schedulers."""

    def as_slurm(self) -> str: ...  # noqa: D102
    def as_pbs(self) -> str: ...  # noqa: D102


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


@dataclass(frozen=True)
class Memory:
    """A scheduler agnostic amount of memory, stored in bytes."""

    _KIB, _MIB, _GIB, _TIB = 2**10, 2**20, 2**30, 2**40
    _UNITS = {"K": _KIB, "M": _MIB, "G": _GIB, "T": _TIB}
    _MEMORY_PATTERN = re.compile(
        r"(\d+(?:\.\d+)?)\s*(?:([KMGT])B?)?", re.IGNORECASE
    )

    size_bytes: int

    def __post_init__(self) -> None:
        """Ensure memory is positive, slurm allows for mem=0 (for all)."""
        if self.size_bytes <= 0:
            raise ValueError("Memory must be positive")

    @classmethod
    def parse(cls, text: str) -> Memory:
        """Parse values like '8G', '8GB', '500M' or '1.5g'.

        A bare number is megabytes (the slurm default). Units are powers of
        1024, matching both slurm and PBS.

        """
        match = cls._MEMORY_PATTERN.fullmatch(text.strip())
        if match is None:
            raise ValueError(f"Invalid memory value: {text!r}")
        number, unit = match.groups()
        scale = cls._UNITS[unit.upper()] if unit else cls._MIB
        return cls(round(float(number) * scale))

    def as_slurm(self) -> str:
        """Return as a slurm --mem value (8G, 500M)."""
        # slurm can only use G and M (so M is min size)
        for suffix, size in (("G", self._GIB), ("M", self._MIB)):
            if self.size_bytes % size == 0:
                return f"{self.size_bytes // size}{suffix}"
        return f"{math.ceil(self.size_bytes / self._MIB)}M"

    def as_pbs(self) -> str:
        """Return as a PBS mem value (8gb, 500mb)."""
        for suffix, size in (
            ("tb", self._TIB),
            ("gb", self._GIB),
            ("mb", self._MIB),
            ("kb", self._KIB),
        ):
            if self.size_bytes % size == 0:
                return f"{self.size_bytes // size}{suffix}"
        return f"{self.size_bytes}b"


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
        metadata={
            "slurm": "--cpus-per-task",
            "pbs": SKIP_DIRECTIVE,  # handled separately
        },
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
    memory: Memory | None = field(
        default=None,
        metadata={
            "slurm": "--mem",
            "pbs": SKIP_DIRECTIVE,  # handled separately
        },
    )
    partition: str | None = field(
        default=None,
        metadata={"slurm": "--partition", "pbs": "-q"},
    )
    qos: str | None = field(
        default=None,
        metadata={"slurm": "--qos", "pbs": SKIP_DIRECTIVE},  # pbs has no 'qos'
    )
    task_count: str | None = field(
        default=None,
        metadata={
            "slurm": "--ntasks",
            "pbs": SKIP_DIRECTIVE,  # handled separately
        },
    )
    wall_time: str | None = field(
        default=None,
        metadata={"slurm": "--time", "pbs": "-l walltime"},
    )

    def _render(self, value: object, scheduler: str) -> str | None:
        """Convert a directive value to its scheduler specific string."""
        if value is None:
            return None
        if isinstance(value, SchedulerValue):
            return getattr(value, f"as_{scheduler}")()
        return str(value)

    def as_slurm(self) -> dict[str, str | None | SKIP_DIRECTIVE]:
        """Return directives as used in slurm."""
        return {
            field.metadata["slurm"]: self._render(
                getattr(self, field.name), "slurm"
            )
            for field in fields(self)
        }

    def as_pbs(self) -> dict[str, str | None | SKIP_DIRECTIVE]:
        """Return directives as used in PBS."""
        result: dict[str, str | None] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            key = f.metadata["pbs"]
            if isinstance(value, CopyEnvironment):
                key = value.pbs_flag
            result[key] = self._render(value, "pbs")
        return result
