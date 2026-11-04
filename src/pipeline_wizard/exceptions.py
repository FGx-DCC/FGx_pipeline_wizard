"""Error classes for pipeline_wizard."""

from pathlib import Path


class NotUpperError(Exception):
    """Raised when a name is not in upper case."""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"'{name}' is not in upper case. Please ensure all "
            "parameters/requirements are in upper case"
        )


class PipelineParseError(Exception):
    """Raised when a pipeline toml file could not be parsed."""

    def __init__(self, error_message: str, file_path: Path) -> None:
        super().__init__(
            f"Pipeline parsing error (for {file_path}): {error_message}"
        )


class NotADagError(Exception):
    """Raised when a pipeline is not a directed acyclic graph."""

    def __init__(self, additional_details: str, file_path: Path) -> None:
        super().__init__(
            f"Pipeline is not a DAG (for {file_path}): {additional_details}"
        )
