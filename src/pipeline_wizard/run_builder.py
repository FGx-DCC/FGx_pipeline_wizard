"""Writer for pipeline wrapper script (entry point for pipeline)."""

import os
from pathlib import Path

from pipeline_wizard.dag import Dag, Step


class RunBuilder:
    """Pipeline writer, module by module.

    It is assumed that the slurm workload manager is to be used to execute each
    job.

    TODO: Add more job executors.

    """

    def __init__(
        self,
        scripts_directory: Path,
        config_path: Path,
        pipeline: Dag,
        starting_step: int,
    ) -> None:
        """Initialise the instance."""
        self._scripts_directory = scripts_directory
        self._config_path = config_path
        self._job_names: dict[str, str] = {}
        self._contents = []
        self._step_counter = starting_step

        self._add_header(pipeline)

    def _add_header(self, pipeline: Dag) -> None:
        """Add top of the run script that will always exist."""
        self._contents.append("#!/bin/bash")
        self._contents.append("")
        self._contents.append("set -euo pipefail")
        self._contents.append("")
        self._contents.append("### " + "=" * 75)  # for a line length of 79
        self._contents.append(f"### {pipeline.name}")
        self._contents.append("### " + "-" * 75)
        self._contents.append(f"### {pipeline.description}")
        self._contents.append("### " + "=" * 75)
        self._contents.append("")
        self._contents.append("")
        self._contents.append(f"source {self._config_path}")
        self._contents.append("")

    def add_pipeline_step(self, step: Step) -> None:
        """Append scripts to run in parallel for next pipeline step."""
        self._contents.append(f"## Step {self._step_counter}")

        for idx, script in enumerate(step, 1):
            job_name = f"jobid_{self._step_counter}_{idx}"
            self._job_names[script.name] = job_name
            full_script_path = self._scripts_directory / script.path
            dependency_job_names = [
                f'"${{{self._job_names[dependent_script.name]}}}"'
                for dependent_script in script.dependencies
                if dependent_script.name in self._job_names
            ]
            opts = (
                "--dependency=afterok:" + ":".join(dependency_job_names)
                if dependency_job_names != []
                else ""
            )
            opts += " --parsable"

            self._contents.append("")

            description = (
                script.description
                if script.description
                else "No description given"
            )
            self._contents.append(f"# {script.name} -> {description}")
            self._contents.append(
                f"{job_name}=$(sbatch {opts} {full_script_path})"  # noqa: E501
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

        os.chmod(out_path, mode=0o755)
