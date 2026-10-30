"""Types used across pipeline_wizard."""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _typeshed import StrPath


class AbsolutePath(Path):
    """An absolute path (from root)."""

    def __init__(self, *pathsegments: StrPath) -> None:
        super().__init__(Path(*pathsegments).expanduser().resolve())
