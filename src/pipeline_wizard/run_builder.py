"""Writer for pipeline wrapper script (entry point for pipeline)."""

import os
from pathlib import Path

from pipeline_wizard.dag import Dag, Step
from pipeline_wizard.executors import LocalExecutor
from pipeline_wizard.types import AbsolutePath


class RunBuilder:
    """Pipeline writer, module by module.

    It is assumed that the slurm workload manager is to be used to execute each
    job.

    TODO: Add more job executors.

    """

    def __init__(
        self,
        scripts_directory: AbsolutePath,
        config_path: AbsolutePath,
        pipeline: Dag,
        starting_step: int,
    ) -> None:
        """Initialise the instance."""
        self._scripts_directory = scripts_directory
        self._config_path = config_path
        self._job_variables: dict[str, str] = {}
        self._contents = []
        self._step_counter = starting_step
        if pipeline.executor is None:
            # fallback (always available)
            self._executor = LocalExecutor()
        else:
            self._executor = pipeline.executor

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
            job_variable = f"jobid_{self._step_counter}_{idx}"
            self._job_variables[script.name] = job_variable
            full_script_path = self._scripts_directory / script.path
            dependency_job_variables = [
                f'"${{{self._job_variables[dependent_script.name]}}}"'
                for dependent_script in script.dependencies
                if dependent_script.name in self._job_variables
            ]
            description = (
                script.description
                if script.description
                else "No description given"
            )
            self._contents.append("")
            self._contents.append(f"# {script.name} -> {description}")
            self._contents.append(
                self._executor.submit_text(
                    full_script_path,
                    job_variable,
                    script.directives,
                    dependency_job_variables,
                )
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
