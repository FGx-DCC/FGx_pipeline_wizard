"""Parse #SBATCH/#PBS header lines of a script into a `Directives` object."""

from __future__ import annotations

import os
import re
import shlex
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import fields

from pipeline_wizard.directives import (
    SKIP_DIRECTIVE,
    CopyEnvironment,
    Directives,
    EventNotification,
    Memory,
    WallTime,
)
from pipeline_wizard.types import AbsolutePath

_SECONDS_IN_MINUTE = 60
_SECONDS_IN_HOUR = 3600
_SECONDS_IN_DAY = 86400

_DIRECTIVE_LINE = re.compile(r"#(?P<prefix>SBATCH|PBS)\s+(?P<options>.*)")
_PREFIX_TO_SCHEDULER = {"SBATCH": "slurm", "PBS": "pbs"}

# Flags that are valid but are not the "canonical" flag stored in the
# Directives field metadata (short forms, alternative spellings).
_SLURM_ALIASES = {
    "-A": "account",
    "-a": "array",
    "-c": "cpus_per_task",
    "-e": "error_file",
    "-J": "job_name",
    "-n": "task_count",
    "-o": "log_file",
    "-p": "partition",
    "-q": "qos",
    "-t": "wall_time",
}
_PBS_ALIASES = {
    "-v": "copy_environment",  # -V is canonical (all), -v is a named list
}

_PBS_BARE_FLAGS = frozenset({"-V"})


class FlagLookupTable:
    """Two way lookup between `Directives` field names and scheduler flags.

    Built from the `Directives` field metadata so the metadata stays the one
    source of truth. Fields whose flag is `SKIP_DIRECTIVE` are not included
    here (the PBS parser handles those via `-l` resources).

    """

    def __init__(
        self, scheduler: str, flag_aliases: Mapping[str, str]
    ) -> None:
        self.scheduler = scheduler
        self.field_to_flag: dict[str, str] = {}
        self.flag_to_field: dict[str, str] = {}

        # PBS: `-l walltime` style entries
        self.resource_to_field: dict[str, str] = {}

        for f in fields(Directives):
            flag = f.metadata[scheduler]
            if flag is SKIP_DIRECTIVE:
                continue
            self.field_to_flag[f.name] = flag
            if flag.startswith("-l "):
                self.resource_to_field[flag[3:]] = f.name
            else:
                self.flag_to_field[flag] = f.name
        self.flag_to_field.update(flag_aliases)


_TABLES = {
    "slurm": FlagLookupTable("slurm", _SLURM_ALIASES),
    "pbs": FlagLookupTable("pbs", _PBS_ALIASES),
}


def _seconds_to_walltime(total_seconds: int) -> WallTime:
    hours, remainder = divmod(total_seconds, _SECONDS_IN_HOUR)
    minutes, seconds = divmod(remainder, _SECONDS_IN_MINUTE)
    return WallTime(hours, minutes, seconds)


def _parse_slurm_walltime(text: str) -> WallTime:
    """Parse M, M:S, H:M:S, D-H, D-H:M or D-H:M:S."""
    days_text, dash, rest = text.strip().partition("-")
    parts = [int(p) for p in (rest if dash else days_text).split(":")]
    if dash:
        units = (_SECONDS_IN_HOUR, _SECONDS_IN_MINUTE, 1)
        days = int(days_text)
    else:
        units = {
            1: (_SECONDS_IN_MINUTE,),
            2: (_SECONDS_IN_MINUTE, 1),
            3: (_SECONDS_IN_HOUR, _SECONDS_IN_MINUTE, 1),
        }.get(len(parts), ())
        days = 0
    if not units or len(parts) > len(units):
        raise ValueError(f"Invalid slurm time: {text!r}")
    return _seconds_to_walltime(
        days * _SECONDS_IN_DAY
        + sum(p * u for p, u in zip(parts, units, strict=True))
    )


def _parse_pbs_walltime(text: str) -> WallTime:
    """Parse [[HH:]MM:]SS (a bare number is seconds)."""
    parts = [int(p) for p in text.strip().split(":")]
    if len(parts) > 3:
        raise ValueError(f"Invalid PBS walltime: {text!r}")
    total = 0
    for part in parts:
        total = total * 60 + part
    return _seconds_to_walltime(total)


def _parse_pbs_memory(text: str) -> Memory:
    """PBS treats a bare number (or a `b` suffix) as bytes."""
    match = re.fullmatch(r"(\d+)\s*b?", text.strip(), re.IGNORECASE)
    if match:
        return Memory(int(match.group(1)))
    return Memory.parse(text)


# Some slurm types (REQUEUE, TIME_LIMIT, ...) have no pbs equivalent, as such
# these are ignored
_SLURM_EVENTS = {
    "NONE": EventNotification.NONE,
    "BEGIN": EventNotification.BEGIN,
    "END": EventNotification.END,
    "FAIL": EventNotification.FAIL,
    "ALL": EventNotification.ALL,
}


def _parse_slurm_events(text: str) -> EventNotification:
    result = EventNotification.NONE
    for token in text.upper().split(","):
        result |= _SLURM_EVENTS.get(token.strip(), EventNotification.NONE)
    return result


_PBS_EVENTS = {
    "b": EventNotification.BEGIN,
    "e": EventNotification.END,
    "a": EventNotification.FAIL,
}


def _parse_pbs_events(text: str) -> EventNotification:
    result = EventNotification.NONE
    for letter in text.strip():
        result |= _PBS_EVENTS.get(letter, EventNotification.NONE)
    return result


def _split_names(text: str) -> tuple[str, ...]:
    return tuple(n for n in (s.strip() for s in text.split(",")) if n)


def _parse_slurm_env(text: str) -> CopyEnvironment:
    names = _split_names(text)
    upper = [n.upper() for n in names]
    if "ALL" in upper:  # `ALL,FOO=bar` extras cannot be represented
        return CopyEnvironment.ALL
    if not names or upper in (["NONE"], ["NIL"]):
        return CopyEnvironment(())
    return CopyEnvironment(names)


def _parse_pbs_env(text: str) -> CopyEnvironment:
    return CopyEnvironment(_split_names(text))


_SLURM_PARSERS: dict[str, Callable[[str], object]] = {
    "copy_environment": _parse_slurm_env,
    "event_notification": _parse_slurm_events,
    "memory": Memory.parse,
    "wall_time": _parse_slurm_walltime,
}
_PBS_PARSERS: dict[str, Callable[[str], object]] = {
    "copy_environment": _parse_pbs_env,
    "event_notification": _parse_pbs_events,
    "memory": _parse_pbs_memory,
    "wall_time": _parse_pbs_walltime,
}
_PARSERS = {"slurm": _SLURM_PARSERS, "pbs": _PBS_PARSERS}


def _iterate_options(
    text: str, bare_flags: frozenset[str] = frozenset()
) -> Iterator[tuple[str, str | None]]:
    """Yield (flag, value) pairs from the option text of a directive line.

    Handles `--flag=value`, `--flag value`, `-f value` and `-fvalue`, and
    trailing `# comments`. Unknown boolean flags (e.g. `--exclusive`) are
    ignored.

    """
    tokens = shlex.split(text, comments=True)
    i = 0
    while i < len(tokens):
        token = tokens[i]
        i += 1
        if not token.startswith("-") or token == "-":
            continue
        if token.startswith("--"):
            flag, equals, value = token.partition("=")
            inline = value if equals else None
        else:
            flag, inline = token[:2], token[2:] or None
        if flag in bare_flags:
            yield flag, None
            continue
        if (
            inline is None
            and i < len(tokens)
            and not tokens[i].startswith("-")
        ):
            inline = tokens[i]
            i += 1
        yield flag, inline


def _parse_pbs_resources(
    text: str, table: FlagLookupTable
) -> Iterator[tuple[str, object]]:
    """Translate the value of a PBS `-l` option (comma separated resources)."""
    for chunk in text.split(","):
        key, _, value = chunk.strip().partition("=")
        if key in table.resource_to_field:  # walltime
            name = table.resource_to_field[key]
            yield name, _PBS_PARSERS[name](value)
        elif key == "mem":
            yield "memory", _parse_pbs_memory(value)
        elif key == "ncpus":
            yield "cpus_per_task", value
        elif key in ("select", "nodes"):
            count, *chunks = value.split(":")
            nodes = int(count) if count.isdigit() else 1
            attrs = dict(c.split("=", 1) for c in chunks if "=" in c)
            if "ncpus" in attrs or "ppn" in attrs:
                yield "cpus_per_task", attrs.get("ncpus", attrs.get("ppn"))
            if "mem" in attrs:
                yield "memory", _parse_pbs_memory(attrs["mem"])
            if "mpiprocs" in attrs:
                yield "task_count", str(nodes * int(attrs["mpiprocs"]))


def _translate(scheduler: str, options: str) -> Iterator[tuple[str, object]]:
    """Translate one directive line's options into (field name, value)."""
    table = _TABLES[scheduler]
    parsers = _PARSERS[scheduler]
    bare = _PBS_BARE_FLAGS if scheduler == "pbs" else frozenset()

    for flag, raw in _iterate_options(options, bare):
        if scheduler == "pbs" and flag == "-V":
            yield "copy_environment", CopyEnvironment.ALL
            continue
        if scheduler == "pbs" and flag == "-l":
            if raw is None:
                raise ValueError("-l is missing a value")
            yield from _parse_pbs_resources(raw, table)
            continue

        name = table.flag_to_field.get(flag)
        if name is None:
            continue
        if raw is None:
            raise ValueError(f"{flag} is missing a value")
        yield name, parsers.get(name, str)(raw)


def _header_lines(lines: Iterable[str]) -> Iterator[str]:
    """Yield the leading comment block (blank lines allowed, as in sbatch)."""
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return
        yield line


def _parse_directives(lines: Iterable[str]) -> Directives:
    """Build a `Directives` from 'header' lines.

    Only `#SBATCH` and `#PBS` lines are considered; the shebang and every
    other comment is ignored. Later lines override earlier ones, except for
    event notifications which are merged. With `strict=False` values that
    cannot be represented (e.g. `--mem=0`, `--time=UNLIMITED`) are skipped;
    with `strict=True` they raise a `ValueError` naming the line.

    """
    found: dict[str, object] = {}
    for line in lines:
        match = _DIRECTIVE_LINE.match(line.strip())
        if match is None:
            continue
        scheduler = _PREFIX_TO_SCHEDULER[match["prefix"]]
        pairs = list(_translate(scheduler, match["options"]))
        for name, value in pairs:
            previous = found.get(name)
            if isinstance(previous, EventNotification) and isinstance(
                value, EventNotification
            ):
                value = previous | value
            found[name] = value
    return Directives(**found)  # type: ignore (messy)


def read_directives(
    script_path: AbsolutePath,
) -> Directives:
    """Read the 'header' of a script and return its `Directives`."""
    if isinstance(script_path, (str, os.PathLike)):
        with open(script_path, encoding="utf-8", errors="replace") as handle:
            header = list(_header_lines(handle))
    else:
        header = list(_header_lines(script_path))
    return _parse_directives(header)
