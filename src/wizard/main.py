"""Main entry point for config wizard"""

import sys
from pathlib import Path

from wizard.wizard import ask_bool, exit_with_message


def main(scripts_directory: Path, config_file: Path, run_script: Path) -> None:
    # \\
    # Preliminary checks
    # //
    handle_previous_run(config_file, run_script)
    if not (scripts_directory.is_dir() and scripts_directory.exists()):
        exit_with_message(f"""
            Scripts directory not found at {scripts_directory}, please raise
            an issue here:
                https://github.com/FGx-DCC/ONT_processing_pipeline/issues
            """)


def handle_previous_run(config_file: Path, run_script: Path):
    """Remove the config + run script if users want to overwrite."""
    if config_file.exists():
        delete_config = ask_bool(f"""
            A config file already exists at {config_file}, would you like to
            delete it?
            """)
        if not delete_config:
            exit_with_message("Exiting...", exit_code=0)

        try:
            config_file.unlink()
        except OSError as exc:
            exit_with_message(f"Could not remove config file: ({exc})")

        try:
            run_script.unlink(missing_ok=True)
        except OSError as exc:
            exit_with_message(f"Could not remove config file: ({exc})")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(f"Usage: {__file__} scripts_directory out_config.txt run.sh")
    scripts_directory = Path(sys.argv[1])
    config_file = Path(sys.argv[2])
    run_script = Path(sys.argv[3])
    main(scripts_directory, config_file, run_script)
