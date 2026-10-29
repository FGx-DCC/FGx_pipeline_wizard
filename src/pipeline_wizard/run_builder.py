"""Writer for run.sh (entry point for pipeline)."""

from pathlib import Path

from pipeline_wizard.dag import Step


class RunBuilder:
    """Pipeline writer, module by module.

    It is assumed that the slurm workload manager is to be used to execute each
    job.

    TODO: Add more job executors.

    """

    def __init__(self, scripts_directory: Path, config_path: Path) -> None:
        """Initialise the instance."""
        self._scripts_directory = scripts_directory
        self._config_path = config_path
        self._job_names: dict[str, str] = {}
        self._contents = []
        self._step_counter = 1

        self._add_header()

    def _add_header(self) -> None:
        """Add top of the run script that will always exist."""
        self._contents.append("#!/bin/bash")
        self._contents.append("")
        self._contents.append("set -euo pipefail")
        self._contents.append("")
        self._contents.append(f"source {self._config_path}")
        self._contents.append("")

    def add_pipeline_step(self, step: Step) -> None:
        """Append scripts to run in parallel for next pipeline step."""
        self._contents.append(f"## Step {self._step_counter}")
        self._contents.append("")

        for idx, script in enumerate(step, 1):
            job_name = f"jobid_{self._step_counter}_{idx}"
            self._job_names[script.name] = job_name
            full_script_path = self._scripts_directory / script.path
            dependency_job_names = [
                self._job_names[dependent_script.name]
                for dependent_script in script.dependencies
            ]
            opts = (
                "--dependency=afterok:" + ":".join(dependency_job_names)
                if dependency_job_names != []
                else ""
            )
            self._contents.append(
                f"{job_name}=$(sbatch {opts} {full_script_path} | awk '{{print $4}}')"  # noqa: E501
            )
        self._contents.append("")

        self._step_counter += 1

    def write_run_script(self, out_path: Path) -> None:
        """Write the contents of the run script to the path.

        Raises:
            OSError:
                If the file handle couldn't be opened to write. In such cases,
                the method should be retried with a different path.

        """
        with open(out_path, mode="w") as run_script:
            run_script.write("\n".join(self._contents))
