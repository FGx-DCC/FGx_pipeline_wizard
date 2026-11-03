"""Job executors for running scripts in a pipeline."""

import getpass
import shutil
import subprocess
from abc import ABCMeta, abstractmethod
from functools import cached_property
from typing import override

from pipeline_wizard.directives import Directives
from pipeline_wizard.exceptions import CommandNotFoundError
from pipeline_wizard.types import AbsolutePath


class Executor(metaclass=ABCMeta):
    """A job executor, like slurm or pbs."""

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
        directives = self._validate_directives(directives)
        if dependent_jobs:
            options.append("--dependency=afterok:" + ":".join(dependent_jobs))
        for directive, value in directives.as_slurm().items():
            if value is None or value == "":
                continue
            options.append(f"{directive}={value}")

        return f"{job_variable}=$(sbatch {' '.join(options)} {script})"

    @cached_property
    def _slurm_user_info(self) -> list[list[str]]:
        """Return list of accounts and qos for user."""
        if shutil.which("sacctmgr") is None:
            raise CommandNotFoundError("sacctmgr")
        user_info = [
            info.split("|")
            for info in subprocess.run(
                [
                    "sacctmgr",
                    "show",
                    "assoc",
                    "-Pn",  # uses | for separator
                    f"user={getpass.getuser()}",
                    "format=account,qos",
                ],
                capture_output=True,
                text=True,
            )
            .stdout.strip()
            .split("\n")
        ]
        return user_info

    @cached_property
    def _slurm_user_accounts(self) -> list[str]:
        return [info[0] for info in self._slurm_user_info]

    @cached_property
    def _slurm_user_qos(self) -> list[str]:
        # For each line in sacctmgr, qos are given as a comma separated list
        return [
            qos for info in self._slurm_user_info for qos in info[1].split(",")
        ]

    @cached_property
    def _slurm_partitions(self) -> list[str]:
        if shutil.which("sinfo") is None:
            raise CommandNotFoundError("sinfo")
        return (
            subprocess.run(
                ["sinfo", "-h", "--format=%P"], capture_output=True, text=True
            )
            .stdout.strip()
            .split("\n")
        )

    def _validate_directives(self, directives: Directives) -> Directives:
        partitions = self._slurm_partitions
        default_partition = ""
        for parititon in partitions:
            if parititon.endswith("*"):  # from sinfo man page
                default_partition = parititon.rstrip("*")
        partitions = [partition.rstrip("*") for partition in partitions]

        if (
            directives.partition is None
            or directives.partition not in partitions
        ):
            directives.partition = default_partition

        if (
            directives.account is None
            or directives.account not in self._slurm_user_accounts
        ):
            directives.account = self._slurm_user_accounts[0]  # arbitrary

        if (
            directives.qos is None
            or directives.qos not in self._slurm_user_qos
        ):
            directives.qos = self._slurm_user_qos[0]  # arbitrary
            if directives.qos == "":  # some clusters don't use qos
                directives.qos = None

        return directives


class LocalExecutor(Executor):
    """Use the shell for the executor (using the shebang line)."""

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
                if value is None or directive.startswith("-l"):
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


def get_available_system_executors() -> list[type[Executor]]:
    """Return all available executors."""
    available_executors: list[type[Executor]] = [LocalExecutor]
    if shutil.which("sbatch") is not None:
        available_executors.append(SlurmExecutor)
    if shutil.which("qsub") is not None:
        available_executors.append(PBSExecutor)
    return available_executors
