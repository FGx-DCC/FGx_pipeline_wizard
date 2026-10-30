"""User prompts for the pipeline wizard."""

from urllib.error import URLError
from urllib.parse import urlparse

from pipeline_wizard.dag import Parameter, Requirement
from pipeline_wizard.download import download_file
from pipeline_wizard.types import AbsolutePath
from pipeline_wizard.wizard import (
    ANSIColors,
    ask,
    ask_bool,
    tell,
)

TODO = sentinel("TODO")


def prompt_for_requirement_path(
    requirement: Requirement,
) -> AbsolutePath | TODO:
    """Get a requirement path for a requirement.

    If the requirement doesn't exist on disk and the requirement instructions
    is in the form of a URL, the file will be downloaded (and then this
    function will return the path to the downloaded file).

    Returns:
        The path to the requiement or `TODO` if the user needs to do something
        themselves.

    """
    while True:
        user_has_file = ask_bool(f"""
            This pipeline requires the file '{requirement.name}'.
            Do you have this file already?
        """)

        if user_has_file:
            requirement_path = AbsolutePath(
                ask(
                    f"""
                    Please provide an absolute/relative path to the file:
                        '{requirement.name}'
                    """,
                    return_type=str,
                )
            )
            if requirement_path.exists():
                return requirement_path
            else:
                tell(
                    f"This path ({requirement_path}) does not exist...",
                    ANSIColors.YELLOW,
                )
        else:
            break

    # likely semantic instructions
    if urlparse(requirement.instructions).scheme not in {
        "http",
        "https",
        "ftp",
    }:
        tell(f"""
             Pipeline instructions say, for '{requirement.name}', you need to:

             {requirement.instructions}

             Please make sure you complete this and add the path to
             '{requirement.name.upper()}' in the configuration file before
             running the pipeline.
             ---
        """)
        return TODO

    should_download = ask_bool(f"""
        Would you like to download the requirement now?
        (from: {requirement.instructions})
    """)

    if should_download:
        destination = AbsolutePath(
            ask(
                "Where do you want to download to? (directory or full path)",
                return_type=str,
                default=f"./{requirement.name}",
            )
        )
        try:
            return download_file(
                requirement.instructions, destination, requirement.name
            )
        except (URLError, ValueError, OSError) as exc:
            tell(
                f"""
                 Failed to download file to {destination} from
                 {requirement.instructions} ({exc})...
                 """,
                ANSIColors.RED,
            )

    tell(f"""
         Please make sure you download this file yourself and add the path
         to '{requirement.name.upper()}' in the configuration file before
         running the pipeline.
         ---
    """)
    return TODO


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
