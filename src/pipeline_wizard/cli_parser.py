"""CLI parser building for pipeline_wizard."""

import argparse

from pipeline_wizard.types import AbsolutePath


def build_parser() -> argparse.ArgumentParser:
    """Argument parsing for the pipeline wizard CLI."""
    parser = argparse.ArgumentParser(
        prog="pipeline_wizard",
        description="A tool to generate pipeline wrappers from toml files",
    )
    parser.add_argument(
        "-d",
        "--debug",
        help="Debug mode (for developers)",
        action="store_true",
    )
    parser.add_argument(
        "scripts_directory",
        help="The absolute/relative path to where scripts for pipeline are",
        type=AbsolutePath,
    )
    parser.add_argument(
        "pipelines_directory",
        help="The absolute/relative path containing pipeline .toml files",
        type=AbsolutePath,
    )
    parser.add_argument(
        "config_file",
        help="Where to output the configuration file to.",
        type=AbsolutePath,
    )
    parser.add_argument(
        "run_script",
        help="Where to output the run.sh pipeline wrapper script to.",
        type=AbsolutePath,
    )
    return parser


class PipelineWizardArgs(argparse.Namespace):
    """The arguments for pipeline_wizard (for lsp)."""

    debug: bool
    scripts_directory: AbsolutePath
    pipelines_directory: AbsolutePath
    config_file: AbsolutePath
    run_script: AbsolutePath
