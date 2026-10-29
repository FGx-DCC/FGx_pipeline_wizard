"""Main entry point for config wizard."""

import sys
from enum import Enum, auto
from itertools import chain
from pathlib import Path
from typing import NoReturn

from pipeline_wizard.config_builder import ConfigBuilder
from pipeline_wizard.dag import Dag, Parameter
from pipeline_wizard.run_builder import RunBuilder
from pipeline_wizard.wizard import (
    ANSIColors,
    ask,
    ask_bool,
    exit_with_message,
    tell,
)


def run(  # noqa: C901
    scripts_directory: Path,
    pipelines_directory: Path,
    config_file: Path,
    run_script: Path,
) -> None:
    """Run the wizard to create run.sh and accompanying config file."""
    # \\
    # Preliminary checks
    # //
    cleanup_previous_run(config_file, run_script)
    validate_directory_existence(scripts_directory, "Scripts directory")
    validate_directory_existence(pipelines_directory, "Pipelines directory")

    # \\
    # Obtain the pipeline the user wants to build from
    # //
    pipelines = list(pipelines_directory.glob("*.toml"))
    if pipelines == []:
        exit_with_message(f"""
            No pipelines could be found in {pipelines_directory}
            Please raise an issue
        """)

    try:
        parsed_pipelines = [
            Dag.from_toml(pipeline, scripts_directory, pipelines_directory)
            for pipeline in pipelines
        ]
    except (ValueError, RuntimeError) as exc:
        exit_with_message(f"Failed to parse a pipeline: {exc}")

    chosen_pipeline: Dag | None = None
    while chosen_pipeline is None:
        pipeline_to_preview = parsed_pipelines[
            ask(
                """
            Which pipeline would you like to build from?
            (after selecting, a visual representation will be printed)
            To exit, press 'CTRL+D' (if you don't want any pipeline)
            """,
                choices=[f"{pipeline!r}" for pipeline in parsed_pipelines],
            )
        ]
        pipeline_to_preview.print_diagram()
        if ask_bool("Would you like to use this pipeline?"):
            chosen_pipeline = pipeline_to_preview

    # \\
    # Alter pipeline to their needs
    # //
    unaltered_pipeline = chosen_pipeline
    while True:
        options = chosen_pipeline.script_names + [
            "Preview",
            "Restart",
            "Finished",
        ]
        option_chosen = options[
            ask(
                """
                Please pick a step (or select 'Finished' if there are none) to
                remove from the pipeline. Any step you pick will also remove
                any dependent steps.

                If you messed up (accidently removed a step you didn't want to)
                use the 'Restart' option.

                If you just want to start the pipeline halfway through, that
                option will come later.

                To view the current state of the pipeline, select 'Preview'
                """,
                choices=options,
            )
        ]
        if option_chosen == "Finished":
            break
        elif option_chosen == "Preview":
            chosen_pipeline.print_diagram()
        elif chosen_pipeline == "Restart":
            tell("Resetting back to unaltered pipeline...")
            chosen_pipeline = unaltered_pipeline
        else:
            chosen_pipeline.prune(option_chosen)

    pipeline_steps = chosen_pipeline.steps
    # ±1 due to 1/0 based indexing switch
    start = (
        ask(
            "What step would you like to start from?",
            choices=[f"Step {i}" for i in range(1, len(pipeline_steps) + 1)],
            default=1,
        )
        - 1
    )
    pipeline_steps = pipeline_steps[start:]

    # \\
    # Write output files
    # //
    config_builder = ConfigBuilder()
    run_script_builder = RunBuilder(scripts_directory, config_file)

    for step in pipeline_steps:
        run_script_builder.add_pipeline_step(step)

    if not run_script.exists():
        run_script_builder.write_run_script(run_script)

    if config_file.exists():
        return

    all_scripts = chain.from_iterable(pipeline_steps)
    all_parameters = chain.from_iterable(
        script.parameters.values() for script in all_scripts
    )

    for parameter in all_parameters:
        config_builder.add_parameter_value_pair(
            parameter, prompt_for_parameter_value(parameter)
        )

    config_builder.write_config_file(config_file)


def prompt_for_parameter_value(parameter: Parameter) -> int | str:
    """Get a parameter value from the user."""
    default = parameter.default

    # A list for the default means this is a set of choices the user can make
    if isinstance(default, list):
        choices = default
        index = ask(
            f"Pick a value for {parameter.name}",
            choices=[str(choice) for choice in choices],
        )
        return choices[index]

    message = f"Choose a value for {parameter.name}"

    if isinstance(default, bool):
        return ask_bool(message)

    if isinstance(default, int):
        return ask(message, return_type=int, default=default)

    return ask(message, return_type=str, default=default)


def validate_directory_existence(
    directory_path: Path, directory_name: str
) -> None:
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


def cleanup_previous_run(config_file: Path, run_script: Path) -> None:
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
            "Both config and run.sh exist and were not deleted, nothing to do",
            exit_code=0,
        )


def usage() -> NoReturn:
    """Print tool usage and exit."""
    exit_with_message(
        f"{ANSIColors.GREEN}Usage: pipeline_wizard scripts_directory "
        f"pipelines_directory out_config.txt run.sh{ANSIColors.RESET}",
        exit_code=0,
    )


def main() -> None:
    """Entry point."""
    if len(sys.argv) >= 2 and (sys.argv[1] == "-h" or sys.argv[1] == "--help"):
        usage()
    if len(sys.argv) != 5:
        usage()
    scripts_directory = Path(sys.argv[1])
    pipelines_directory = Path(sys.argv[2])
    config_file = Path(sys.argv[3])
    run_script = Path(sys.argv[4])
    run(scripts_directory, pipelines_directory, config_file, run_script)


if __name__ == "__main__":
    main()
