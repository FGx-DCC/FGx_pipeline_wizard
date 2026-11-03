"""Job executors for running scripts in a pipeline."""

import getpass
import shutil
import subprocess
from abc import ABCMeta, abstractmethod
from dataclasses import fields
from functools import cached_property
from typing import override

from pipeline_wizard.exceptions import CommandNotFoundError
from pipeline_wizard.script import Directives
from pipeline_wizard.types import AbsolutePath


class Executor(metaclass=ABCMeta):
    """A job executor, like slurm or pbs."""

    @abstractmethod
    def submit_text(
        self,
        script: AbsolutePath,
        job_name: str,
        directives: Directives | None,
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

    _DIRECTIVES_MAP = {
        "account": "--account=",
        "partition": "--partition=",
        "job_name": "--job-name=",
        "array": "--array=",
        "copy_environment": "--export=",
        "cpus_per_task": "--cpus-per-task=",
        "error_file": "--error=",
        "log_file": "--output=",
        "memory": "--mem=",
        "qos": "--qos=",
        "wall_time": "--time=",
        "event_notification": "--mail-type=",
        "task_count": "--ntasks=",
    }

    @override
    def submit_text(
        self,
        script: AbsolutePath,
        job_name: str,
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
        for field in fields(directives):
            field_value = getattr(directives, field.name)
            if field_value is not None and field_value != "":
                if field.name == "copy_environment":
                    field_value = "ALL"
                options.append(
                    f"{self._DIRECTIVES_MAP[field.name]}{field_value}"
                )

        return f"{job_name}=$(sbatch {' '.join(options)} {script})"

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
        return [info[1] for info in self._slurm_user_info]

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
                default_partition = parititon

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
        job_name: str,
        directives: Directives | None,
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
        directives: Directives | None,
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
