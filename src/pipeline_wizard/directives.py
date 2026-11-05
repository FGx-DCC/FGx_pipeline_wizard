"""Translation layer for different job executor directives."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, fields
from datetime import timedelta
from enum import Flag, auto
from typing import Protocol, runtime_checkable


@runtime_checkable
class SchedulerValue(Protocol):
    """A value that can be converted for different schedulers."""

    def as_slurm(self) -> str: ...  # noqa: D102
    def as_pbs(self) -> str: ...  # noqa: D102


class WallTime(timedelta):
    """A datetime.timedelta class implementing the SchedulerValue protocol.

    We use timedelta here as time doesn't go above 1 day (which many jobs can
    have).

    """

    _SECONDS_IN_MINUTE = 60
    _SECONDS_IN_HOUR = 3600

    def as_slurm(self) -> str:
        """Return as a slurm --time value."""
        hours, seconds = divmod(self.seconds, self._SECONDS_IN_HOUR)
        minutes, seconds = divmod(seconds, self._SECONDS_IN_MINUTE)
        return f"{self.days}-{hours}:{minutes}:{seconds}"

    def as_pbs(self) -> str:
        """Return as a pbs -l walltime value."""
        hours, seconds = divmod(
            int(self.total_seconds()), self._SECONDS_IN_HOUR
        )
        minutes, seconds = divmod(seconds, self._SECONDS_IN_MINUTE)
        return f"{hours}:{minutes}:{seconds}"


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

    array: str | None = field(
        default=None,
        metadata={"slurm": "--array", "pbs": "-J"},
    )
    cpus_per_task: str | None = field(
        default=None,
        metadata={
            "slurm": "--cpus-per-task",
        },
    )
    # Slurm allows for filename patters (%u, %x, %j), but pbs does not.
    # Therefore we just treat file paths as pure strings and ignore this
    # detail.
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
        },
    )
    nodes: str | None = field(
        default=None,
        metadata={"slurm": "--nodes"},
    )
    task_count: str | None = field(
        default=None,
        metadata={
            "slurm": "--ntasks",
        },
    )
    wall_time: WallTime | None = field(
        default=None,
        metadata={"slurm": "--time"},
    )

    def _render(self, value: object, scheduler: str) -> str | None:
        """Convert a directive value to its scheduler specific string."""
        if value is None:
            return None
        if isinstance(value, SchedulerValue):
            match scheduler:
                case "slurm":
                    return value.as_slurm()
                case "pbs":
                    return value.as_pbs()
        return str(value)

    def as_slurm(self) -> dict[str, str | None]:
        """Return directives as used in slurm."""
        return {
            field.metadata["slurm"]: self._render(
                getattr(self, field.name), "slurm"
            )
            for field in fields(self)
            if "slurm" in field.metadata
        }

    def as_pbs(self) -> dict[str, str | None]:
        """Return directives as used in PBS."""
        result: dict[str, str | None] = {}
        for f in fields(self):
            if "pbs" not in f.metadata:
                continue
            value = getattr(self, f.name)
            key = f.metadata["pbs"]
            result[key] = self._render(value, "pbs")
        return result
