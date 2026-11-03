"""Job executors for running scripts in a pipeline."""

import shutil
from abc import ABCMeta, abstractmethod
from typing import override

from pipeline_wizard.types import AbsolutePath


class Executor(metaclass=ABCMeta):
    """A job executor, like slurm or pbs."""

    @abstractmethod
    def submit_text(
        self,
        script: AbsolutePath,
        job_name: str,
        directives: list[str] | None,
        dependent_jobs: list[str] | None,
    ) -> str:
        """Return line for the pipeline wrapper script to submit the job.

        Args:
            script:
                The script to submit to the executor.
            job_name:
                The name of the variable to put the job id (if any) into.
            directives:
                The executor directives/options to add to the submit line.
            dependent_jobs:
                The list of job names that this script depends on before it can
                run.

        """


class SlurmExecutor(Executor):
    """The slurm workload manager."""

    @override
    def submit_text(
        self,
        script: AbsolutePath,
        job_name: str,
        directives: list[str] | None,
        dependent_jobs: list[str] | None,
    ) -> str:
        """Return submit line for sbatch."""
        return ""


class LocalExecutor(Executor):
    """Use the shell for the executor (using the shebang line)."""

    @override
    def submit_text(
        self,
        script: AbsolutePath,
        job_name: str,
        directives: list[str] | None,
        dependent_jobs: list[str] | None,
    ) -> str:
        """Return submit line for shell."""
        return ""


class PBSExecutor(Executor):
    """Portable Batch System."""

    @override
    def submit_text(
        self,
        script: AbsolutePath,
        job_name: str,
        directives: list[str] | None,
        dependent_jobs: list[str] | None,
    ) -> str:
        """Return submit line for qsub."""
        return ""


def get_available_system_executors() -> list[type[Executor]]:
    """Return all available executors."""
    available_executors: list[type[Executor]] = [LocalExecutor]
    if shutil.which("sbatch") is not None:
        available_executors.append(SlurmExecutor)
    if shutil.which("qsub") is not None:
        available_executors.append(PBSExecutor)
    return available_executors
