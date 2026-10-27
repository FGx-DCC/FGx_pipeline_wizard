"""Writer for run.sh (entry point for pipeline)."""

from pathlib import Path

from wizard.scripts import Script


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
        self._contents = []
        self._step_counter = 1
        self._previous_jobids = []

    def header(self) -> None:
        self._contents.append("#!/bin/bash")
        self._contents.append("")
        self._contents.append(f"source {self._config_path}")
        self._contents.append("")

    def add_pipeline_step(self, scripts: list[Script]) -> None:
        """Append scripts to run in parallel for next pipeline step."""
        self._contents.append(f"## Step {self._step_counter}")
        self._contents.append("")

        jobids = []
        for idx, script in enumerate(scripts, 1):
            jobid_variable = f"jobid_{self._step_counter}_{idx}"
            jobids.append(jobid_variable)
            full_script_path = self._scripts_directory / script.path
            opts = (
                "--dependency=afterok:" + ",".join(self._previous_jobids)
                if self._previous_jobids != []
                else ""
            )
            self._contents.append(
                f"{jobid_variable}=$(sbatch {opts} {full_script_path})"
            )
        self._contents.append("")

        self._step_counter += 1
        self._previous_jobids = jobids

    def write_run_script(self, out_path: Path) -> None:
        """Write the contents of the run script to the path.

        Raises:
            OSError:
                If the file handle couldn't be opened to write. In such cases,
                the method should be retried with a different path.

        """
        with open(out_path, mode="w") as run_script:
            run_script.writelines(self._contents)
