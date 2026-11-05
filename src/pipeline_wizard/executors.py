"""Job executors for running scripts in a pipeline."""

import shlex
import shutil
from abc import ABCMeta, abstractmethod
from typing import override

from pipeline_wizard.directives import Directives
from pipeline_wizard.types import AbsolutePath


class Executor(metaclass=ABCMeta):
    """A job executor, like slurm or pbs."""

    @override
    def __eq__(self, other: object) -> bool:
        """Return True if other is an Executor with the same name."""
        if not isinstance(other, Executor):
            return False

        return self.executor_name() == other.executor_name()

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

    def _construct_command(
        self,
        variable: str,
        commands: list[str],
        command_arguments: dict[str, list[str]],
    ) -> str:
        r"""Construct a command such that it takes up minimal width.

        Returns:
            var=$(\
                command \
                -option value \
                -option=value \
                --flag \
                argument \
                argument \
                | \
                command \
                --option=value \
                -flag \
                argument \
            )

        """
        command_components = [f"{variable}=$(\\\n"]
        for idx, command in enumerate(commands, 1):
            formatted_command = f"\t{command} \\\n"
            formatted_arguments = [
                f"\t{argument} \\\n"
                for argument in command_arguments.get(command, "")
            ]
            command_components.append(
                f"{formatted_command}{''.join(formatted_arguments)}"
            )
            if len(commands) > 1 and idx < len(commands):
                command_components.append("\t| \\\n")

        return "".join(command_components) + ")"


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
        if directives is None:
            raise ValueError("Directives required for slurm scripts")

        sbatch_arguments = ["--parsable"]
        if dependent_jobs:
            sbatch_arguments.append(
                "--dependency=afterok:" + ":".join(dependent_jobs)
            )
        for directive, value in directives.as_slurm().items():
            if value is None or value == "":
                continue
            sbatch_arguments.append(f"{directive}={shlex.quote(value)}")

        sbatch_arguments.append(str(script))

        # cut for cases where multiple clusters exist on system
        commands = ["sbatch", "cut"]
        command_arguments = {
            "sbatch": sbatch_arguments,
            "cut": ["-d';'", "-f1"],
        }
        return self._construct_command(
            job_variable, commands, command_arguments
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
        if directives is None:
            raise ValueError("Directives required for pbs scripts")

        qsub_arguments = []
        if dependent_jobs:
            qsub_arguments.append(
                "-W depend=afterok:" + ":".join(dependent_jobs)
            )
        for directive, value in directives.as_pbs().items():
            if value is None:
                continue
            # Edge case where script copies specific environvironment variables
            # but there are no variables to copy
            if directive == "-v" and value == "":
                continue
            qsub_arguments.append(
                directive
                if value == ""
                else f"{directive} {shlex.quote(value)}"
            )
        qsub_arguments.extend(self._resource_options(directives))
        qsub_arguments.append(str(script))

        commands = ["qsub"]
        command_arguments = {"qsub": qsub_arguments}
        return self._construct_command(
            job_variable, commands, command_arguments
        )

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
            resources.append(f"-l walltime={directives.wall_time.as_pbs()}")

        return resources


def get_available_system_executors() -> list[Executor]:
    """Return all available executors."""
    available_executors: list[Executor] = [LocalExecutor()]
    if shutil.which("sbatch") is not None:
        available_executors.append(SlurmExecutor())
    if shutil.which("qsub") is not None:
        available_executors.append(PBSExecutor())
    return available_executors
