"""Main entry point for config wizard."""

from enum import Enum, auto
from itertools import chain
from pathlib import Path

from pipeline_wizard.cli_parser import PipelineWizardArgs
from pipeline_wizard.config_builder import ConfigBuilder
from pipeline_wizard.dag import Dag, Parameter, Requirement
from pipeline_wizard.exceptions import NotADagError, PipelineParseError
from pipeline_wizard.prompts import (
    prompt_for_parameter_value,
    prompt_for_requirement_path,
)
from pipeline_wizard.run_builder import RunBuilder
from pipeline_wizard.wizard import (
    ANSIColors,
    ask,
    ask_bool,
    exit_with_message,
    tell,
)


def run(  # noqa: C901
    args: PipelineWizardArgs,
) -> None:
    """Run the wizard to create wrapper script and accompanying config file."""
    # \\
    # Preliminary checks
    # //
    _cleanup_previous_run(args.config_file, args.run_script)
    _validate_directory_existence(args.scripts_directory, "Scripts directory")
    _validate_directory_existence(
        args.pipelines_directory, "Pipelines directory"
    )

    # \\
    # Obtain the pipeline the user wants to build from
    # //
    pipelines = list(args.pipelines_directory.glob("*.toml"))
    if pipelines == []:
        exit_with_message(f"""
            No pipelines could be found in {args.pipelines_directory}
            Please raise an issue
        """)

    try:
        parsed_pipelines = [
            Dag.from_toml(
                pipeline, args.scripts_directory, args.pipelines_directory
            )
            for pipeline in pipelines
        ]
        # check pipelines are valid dags
        [pipeline.steps for pipeline in parsed_pipelines]
    except (NotADagError, PipelineParseError) as exc:
        exit_with_message(f"{exc}")

    chosen_pipeline: Dag | None = None
    while chosen_pipeline is None:
        pipeline_to_preview = parsed_pipelines[
            ask(
                """
            Which pipeline would you like to build from?
            (after selecting, a visual representation will be printed)
            To exit, press 'CTRL+D' (if you don't want any pipeline)
            """,
                choices=[
                    f"{pipeline.title()}" for pipeline in parsed_pipelines
                ],
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
                ===============
                PIPELINE EDITOR
                ===============
                Please pick a step (or select 'Finished' if there are none) to
                remove from the pipeline. Any step you pick will also remove
                any dependent steps.

                If you messed up (accidentally removed a step) use the
                'Restart' option.

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
            ask(
                "Hit enter to go back to editor",
                return_type=str,  # using str here in case they type anything
                default="back to editor",  # not used, but is shown in prompt
            )
        elif option_chosen == "Restart":
            tell("Resetting back to unaltered pipeline...", ANSIColors.GREEN)
            chosen_pipeline = unaltered_pipeline
        else:
            chosen_pipeline = chosen_pipeline.prune(option_chosen)

    if chosen_pipeline.empty:
        exit_with_message(
            f"""
            You removed all steps from the pipeline
            there is nothing to write to {args.run_script}...
            """,
            exit_code=0,
        )

    pipeline_steps = chosen_pipeline.steps
    # ±1 due to 1/0 based indexing switch
    start = ask(
        "What step would you like to start from?",
        choices=[f"Step {i}" for i in range(1, len(pipeline_steps) + 1)],
        default=0,
    )
    pipeline_steps = pipeline_steps[start:]

    # \\
    # Write output files
    # //
    config_builder = ConfigBuilder()
    run_script_builder = RunBuilder(
        args.scripts_directory, args.config_file, chosen_pipeline, start + 1
    )

    all_parameters = chain(
        chain.from_iterable(
            script.parameters.values()
            for script in chain.from_iterable(pipeline_steps)
        ),
        chosen_pipeline.global_parameters.values(),
    )
    all_requirements = chain.from_iterable(
        script.requires.values()
        for script in chain.from_iterable(pipeline_steps)
    )

    if not args.config_file.exists():
        _build_config_file(config_builder, all_parameters, all_requirements)
        config_builder.write_config_file(args.config_file)
        tell(
            f"Created configuration file at {args.config_file}",
            ANSIColors.GREEN,
        )

    if not args.run_script.exists():
        for step in pipeline_steps:
            run_script_builder.add_pipeline_step(step)
        run_script_builder.write_run_script(args.run_script)
        tell(f"Created run script at {args.run_script}", ANSIColors.GREEN)


def _build_config_file(
    builder: ConfigBuilder,
    parameters: chain[Parameter],
    requirements: chain[Requirement],
) -> None:
    """Build the configuration file."""
    tell("""
         We will now gather parameter values and external requirements to build
         the configuration file. For each choice, The default value for each
         parameter will appear on the left inside of the square brackets. These
         defaults have been chosen by the pipeline creator, so only change them
         if you know what you are doing.
         ---
    """)

    for parameter in parameters:
        if parameter.name in builder.parameters:
            continue
        builder.add_parameter_value_pair(
            parameter, prompt_for_parameter_value(parameter)
        )

    for requirement in requirements:
        if requirement.name in builder.requirements:
            continue
        builder.add_requirement_path_pair(
            requirement, prompt_for_requirement_path(requirement)
        )


def _validate_directory_existence(
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


class _FileDeletionResult(Enum):
    """Result of deleting a file."""

    DELETED = auto()
    KEPT = auto()
    NOTHING_TO_DELETE = auto()


def _cleanup_previous_run(config_file: Path, run_script: Path) -> None:
    """Remove the config + run script if users want to overwrite them.

    In the event that neither file is to be overwritten, then there is nothing
    more for this tool to do. In such an event, the tool exits early.

    """

    def delete_file(path: Path, file_name: str) -> _FileDeletionResult:
        """Delete a file if it exists and user wants to delete it.

        If a file couldn't be deleted (some error such as a permissions error),
        the program crashes with the associated error message.

        """
        if path.exists():
            delete_file = ask_bool(f"""
            {file_name} already exists at {path}, would you like to delete it?
            """)
            if not delete_file:
                return _FileDeletionResult.KEPT
            try:
                path.unlink()
                return _FileDeletionResult.DELETED
            except OSError as exc:
                exit_with_message(f"Could not remove {file_name}: ({exc})")
        return _FileDeletionResult.NOTHING_TO_DELETE

    config_deleted = delete_file(config_file, "configuration file")
    run_script_deleted = delete_file(run_script, "pipeline wrapper script")

    if (
        config_deleted == _FileDeletionResult.KEPT
        and run_script_deleted == _FileDeletionResult.KEPT
    ):
        exit_with_message(
            """
            Both config and pipeline wrapper scirpt exist and were not deleted,
            nothing to do...
            """,
            exit_code=0,
        )

    if (
        config_deleted == _FileDeletionResult.KEPT
        and run_script_deleted == _FileDeletionResult.DELETED
    ):
        tell(
            """
            WARNING: Deleting the config but not the run script could lead to
            missing parameters. Please only do this if you know what you are
            doing or you are pruning the run script.
            """,
            ANSIColors.YELLOW,
        )
