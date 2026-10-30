"""CLI parser building for pipeline_wizard."""

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _typeshed import StrPath


class _AbsolutePath(Path):
    """An absolute path (from root)."""

    def __init__(self, *pathsegments: StrPath) -> None:
        super().__init__(Path(*pathsegments).expanduser().resolve())


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
        type=_AbsolutePath,
    )
    parser.add_argument(
        "pipelines_directory",
        help="The absolute/relative path containing pipeline .toml files",
        type=_AbsolutePath,
    )
    parser.add_argument(
        "config_file",
        help="Where to output the configuration file to.",
        type=_AbsolutePath,
    )
    parser.add_argument(
        "run_script",
        help="Where to output the run.sh pipeline wrapper script to.",
        type=_AbsolutePath,
    )
    return parser


class PipelineWizardArgs(argparse.Namespace):
    """The arguments for pipeline_wizard (for lsp)."""

    debug: bool
    scripts_directory: _AbsolutePath
    pipelines_directory: _AbsolutePath
    config_file: _AbsolutePath
    run_script: _AbsolutePath
