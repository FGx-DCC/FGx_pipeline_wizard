"""Job executors for running scripts in a pipeline."""

import shutil


def get_available_system_executors() -> list[str]:
    """Return all available executors."""
    available_executors = ["local"]  # always available
    if shutil.which("sbatch") is not None:
        available_executors.append("slurm")
    if shutil.which("qsub") is not None:
        available_executors.append("pbs")
    return available_executors
