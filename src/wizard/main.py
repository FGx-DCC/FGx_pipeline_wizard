"""Main entry point for config wizard"""

import sys
from enum import Enum, auto
from pathlib import Path

from wizard.wizard import ask_bool, exit_with_message


def main(
    scripts_directory: Path,
    pipelines_directory: Path,
    config_file: Path,
    run_script: Path,
) -> None:
    # \\
    # Preliminary checks
    # //
    cleanup_previous_run(config_file, run_script)
    validate_directory_existence(scripts_directory, "Scripts directory")
    validate_directory_existence(pipelines_directory, "Pipelines directory")


def validate_directory_existence(directory_path: Path, directory_name: str):
    """Check a path is a valid directory and exists.

    This is quite weak, as of course, the expectant files may not exist within
    said directories. Another part of the tool needs to check that the
    expectant files are within this directory.

    If the directory doesn't exist, the tool exits immediately.

    """
    if not (directory_path.is_dir() and directory_path.exists()):
        exit_with_message(f"""
            {directory_name} was not found at {directory_path}, please raise
            an issue.
        """)


class FileDeletionResult(Enum):
    """Result of deleteing a file."""

    DELETED = auto()
    KEPT = auto()
    NOTHING_TO_DELETE = auto()


def cleanup_previous_run(config_file: Path, run_script: Path):
    """Remove the config + run script if users want to overwrite them.

    In the event that neither file is to be overwritten, then there is nothing
    more for this tool to do. In such an event, the tool exits early.

    """

    def delete_file(path: Path, file_name: str) -> FileDeletionResult:
        """Delete a file if it exists and user wants to delete it.

        If a file couldn't be deleted (some error such as a permissions error),
        the program crashes with the associated error message.

        """
        if path.exists():
            delete_file = ask_bool(f"""
            {file_name} already exists at {path}, would you like to delete it?
            """)
            if not delete_file:
                return FileDeletionResult.KEPT
            try:
                path.unlink()
                return FileDeletionResult.DELETED
            except OSError as exc:
                exit_with_message(f"Could not remove {file_name}: ({exc})")
        return FileDeletionResult.NOTHING_TO_DELETE

    config_deleted = delete_file(config_file, "configuration file")
    run_script_deleted = delete_file(run_script, "run.sh")

    if (
        config_deleted == FileDeletionResult.KEPT
        and run_script_deleted == FileDeletionResult.KEPT
    ):
        exit_with_message(
            "Both config and run.sh exist and were not deleted, nothing to do...",
            exit_code=0,
        )


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(
            f"Usage: {__file__} scripts_directory pipelines_directory out_config.txt run.sh"
        )
    scripts_directory = Path(sys.argv[1])
    pipelines_directory = Path(sys.argv[2])
    config_file = Path(sys.argv[3])
    run_script = Path(sys.argv[4])
    main(scripts_directory, pipelines_directory, config_file, run_script)
