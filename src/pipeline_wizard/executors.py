"""Job executors for running scripts in a pipeline."""

from dataclasses import replace
import getpass
import shutil
import subprocess
from abc import ABCMeta, abstractmethod
from functools import cached_property
from typing import override

from pipeline_wizard.directives import SKIP_DIRECTIVE, Directives
from pipeline_wizard.exceptions import CommandNotFoundError
from pipeline_wizard.types import AbsolutePath


class Executor(metaclass=ABCMeta):
    """A job executor, like slurm or pbs."""

    @abstractmethod
    def executor_name(self) -> str:
        """Return the name of the executor."""

    @abstractmethod
    def submit_text(
        self,
        script: AbsolutePath,
        job_variable: str,
        directives: Directives | None,
        dependent_jobs: list[str] | None,
    ) -> str:
        """Return line for the pipeline wrapper script to submit the job.

        Args:
            script:
                The script to submit to the executor.
            job_variable:
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
    def executor_name(self) -> str:
        """Return the name of the executor."""
        return "slurm"

    @override
    def submit_text(
        self,
        script: AbsolutePath,
        job_variable: str,
        directives: Directives | None,
        dependent_jobs: list[str] | None,
    ) -> str:
        """Return submit line for sbatch."""
        if not directives:
            raise ValueError("Directives required for slurm scripts")
        options = ["--parsable"]

        if self._qos_options and directives.qos not in self._qos_options:
            # If there are qos on the machine, it is likely enforced, we'll go
            # with the first one at random for now.
            directives = replace(directives, qos=self._qos_options[0])

        if dependent_jobs:
            options.append("--dependency=afterok:" + ":".join(dependent_jobs))
        for directive, value in directives.as_slurm().items():
            if value is None or value == "":
                continue
            options.append(f"{directive}={value}")

        return f"{job_variable}=$(sbatch {' '.join(options)} {script})"

    @cached_property
    def _qos_options(self) -> set[str]:
        """Get all quality of service from sacctmgr if it exists."""
        if shutil.which("sacctmgr") is None:
            raise CommandNotFoundError("sacctmgr")
        return set(
            subprocess.run(
                [
                    "sacctmgr",
                    "show",
                    "assoc",
                    "-Pn",  # uses | for separator
                    f"user={getpass.getuser()}",
                    "format=qos",
                ],
                capture_output=True,
                text=True,
            )
            .stdout.strip()
            .replace("\n", ",")
            .split(",")
        )


class LocalExecutor(Executor):
    """Use the shell for the executor (using the shebang line)."""

    @override
    def executor_name(self) -> str:
        """Return the name of the executor."""
        return "local (bash)"

    @override
    def submit_text(
        self,
        script: AbsolutePath,
        job_variable: str,
        directives: Directives | None,
        dependent_jobs: list[str] | None,
    ) -> str:
        """Return submit line for shell.

        For now, the local executor is incredibly basic and doesn't take
        advantage of parallel jobs. The fix would be to run jobs in the
        background and use 'wait' (though this is a little fragile).

        """
        return str(script)


class PBSExecutor(Executor):
    """Portable Batch System."""

    @override
    def executor_name(self) -> str:
        """Return the name of the executor."""
        return "PBS"

    @override
    def submit_text(
        self,
        script: AbsolutePath,
        job_variable: str,
        directives: Directives | None,
        dependent_jobs: list[str] | None,
    ) -> str:
        """Return submit line for qsub."""
        options = []
        if dependent_jobs:
            options.append("-W depend=afterok:" + ":".join(dependent_jobs))

        if directives:
            for directive, value in directives.as_pbs().items():
                if value is None or directive == SKIP_DIRECTIVE:
                    continue
                options.append(
                    directive if value == "" else f"{directive} {value}"
                )
            options.extend(self._resource_options(directives))

        return f"{job_variable}=$(qsub {' '.join(options)} {script})"

    def _resource_options(self, directives: Directives) -> list[str]:
        """Return the -l resource options for qsub."""
        resources: list[str] = []

        if any(
            (
                directives.cpus_per_task,
                directives.task_count,
                directives.memory,
            )
        ):
            cpus = int(directives.cpus_per_task or 1)
            tasks = int(directives.task_count or 1)
            select = f"select=1:ncpus={cpus * tasks}:mpiprocs={tasks}"
            if cpus > 1:
                select += f":ompthreads={cpus}"
            if directives.memory:
                select += f":mem={directives.memory.as_pbs()}"
            resources.append(f"-l {select}")

        if directives.wall_time:
            resources.append(f"-l walltime={directives.wall_time}")

        return resources


def get_available_system_executors() -> list[Executor]:
    """Return all available executors."""
    available_executors: list[Executor] = [LocalExecutor()]
    if shutil.which("sbatch") is not None:
        available_executors.append(SlurmExecutor())
    if shutil.which("qsub") is not None:
        available_executors.append(PBSExecutor())
    return available_executors
