"""Main entry point for CLI."""

import sys

from pipeline_wizard.cli_parser import PipelineWizardArgs, build_parser
from pipeline_wizard.main import run


def cli() -> None:
    """Entry point for pipeline_wizard."""
    parser = build_parser()
    args = parser.parse_args(namespace=PipelineWizardArgs())
    try:
        run(args)
    except Exception as exc:
        if args.debug:
            raise
        else:
            print(f"FATAL ERROR occurred: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    cli()
