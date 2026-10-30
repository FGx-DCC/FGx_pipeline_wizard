"""Generation of directed acyclic graphs describing pipelines."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from functools import cached_property
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

from pipeline_wizard.exceptions import NotADagError, PipelineParseError
from pipeline_wizard.wizard import ANSIColors, tell


@dataclass
class Parameter:
    """Represents a configuration parameter (such as a file path)."""

    name: str
    """The name of the parameter (to put into the config file)."""

    default: str | int | bool | list[str] | list[int]
    """The default value used for the parameter."""


@dataclass
class Requirement:
    """Represents an external requirement for the pipeline (a reference)."""

    name: str
    """The name of the requirement (to put into the config file)"""

    instructions: str
    """Instructions or a URL on how to get said requirement.

    If this is a valid URL and the user doesn't have the file, the file will
    be retrieved via said URL.

    """


@dataclass
class Script:
    """Represents a script with associated information."""

    name: str
    """Name of script."""

    path: Path
    """Absolute path to the script."""

    description: str
    """What the script attempts to do."""

    dependencies: list[Script] = field(default_factory=list)
    """Scripts required to be completed for this to run."""

    parameters: dict[str, Parameter] = field(default_factory=dict)
    """Configuration parameters needed."""

    requires: dict[str, Requirement] = field(default_factory=dict)
    """File dependencies (for example, a reference genome)."""


Step = tuple[Script, ...]


class Dag:
    """A directed acyclic graph describing a pipeline."""

    def __init__(
        self,
        name: str,
        description: str,
        file_path: Path,
        scripts: dict[str, Script],
        script_dependencies: dict[str, set[str]],
        global_parameters: dict[str, Parameter],
    ) -> None:
        """Initialise the instance."""
        self.name = name
        self.description = description
        self.file_path = file_path
        self._scripts = scripts
        self._script_dependencies = script_dependencies
        self.global_parameters = global_parameters

    def title(self) -> str:
        """Return title of the pipeline."""
        return f"{self.name}: {self.description}"

    @classmethod
    def from_toml(
        cls, path: Path, script_directory: Path, dag_directory: Path
    ) -> Dag:
        """Read DAG from a toml file.

        Example toml file::

            name = "Test Pipeline"
            description = "A test pipeline with read, clean and write steps"

            [parameters]
            out_directory = "/path/to/output/directory/"
            keep_temporary = false

            [steps.read]
            path = "read.sh"
            description = "Read the data from a file and convert to pandas"

            [steps.clean]
            path = "clean.sh"
            description = "Use interpolation to remove missingness"
            after = ["read"]
            [steps.clean.requires]
            reference = "https://www.example.com/reference"
            [steps.clean.parameters]
            max_distance = 5
            tool_version = ["v1","v2"]

            [steps.write]
            path = "write.sh"
            after = ["clean"]

            [steps.report]
            dag = "report.toml" # report.toml looks like this one
            after = ["write"]

        """
        with path.open("rb") as dag_toml:
            data = tomllib.load(dag_toml)

        data["file_path"] = path
        return cls._from_dict(data, script_directory, dag_directory)

    @property
    def empty(self) -> bool:
        """Returns True if pipeline has no steps."""
        return len(self.steps) == 0

    @cached_property
    def steps(self) -> list[Step]:
        """Layers of scripts that can be ran in parallel.

        Raises:
            NotADagError: If there is a cycle in the pipeline

        """
        sorter = TopologicalSorter(self._script_dependencies)
        try:
            sorter.prepare()
        except CycleError as exc:
            raise NotADagError(
                "There is a cycle in your pipeline", self.file_path
            ) from exc
        layers: list[Step] = []
        while sorter.is_active():
            ready = sorter.get_ready()
            layers.append(tuple(self._scripts[n] for n in sorted(ready)))
            sorter.done(*ready)
        return layers

    def print_diagram(self) -> None:
        """Print the pipeline top-down as layers of boxes."""
        if self.empty:
            print("Pipeline is empty...")
            return

        def box(script: Script) -> list[str]:
            dependencies = sorted(self._script_dependencies[script.name])
            lines = [script.name]
            if dependencies:
                lines.append("after: " + ", ".join(dependencies))
            inner = max(len(line) for line in lines)
            return [
                "┌" + "─" * (inner + 2) + "┐",
                *(f"│ {line.ljust(inner)} │" for line in lines),
                "└" + "─" * (inner + 2) + "┘",
            ]

        blocks: list[list[str]] = []
        for layer in self.steps:
            boxes = [box(script) for script in layer]
            height = max(len(b) for b in boxes)
            rows = [
                "   ".join(
                    b[i] if i < len(b) else " " * len(b[0]) for b in boxes
                )
                for i in range(height)
            ]
            blocks.append(rows)

        canvas_width = max(len(row) for rows in blocks for row in rows)
        print(self.name.center(canvas_width))
        print("-" * canvas_width)
        print(self.description.center(canvas_width))
        print("═" * canvas_width)
        for index, rows in enumerate(blocks):
            if index:
                print("│".center(canvas_width))
                print("▼".center(canvas_width))
            for row in rows:
                print(row.center(canvas_width))

    def prune(self, script_name: str) -> Dag:
        """Return a copy of the DAG without the given script or dependents.

        Any step that depends (directly or transitively) on a removed step
        is also removed, since it could no longer run.

        Raises:
            ValueError: If a name is not a step in the pipeline

        """
        if script_name not in self.script_names:
            raise ValueError("This is not a script in the pipeline")

        # Invert the dependency mapping to be able to walk downwards rather
        # than upwards
        dependents: dict[str, set[str]] = {
            name: set() for name in self._scripts
        }
        for node, dependencies in self._script_dependencies.items():
            for dependency in dependencies:
                dependents[dependency].add(node)

        removed: set[str] = set()
        to_visit = [script_name]
        while to_visit:
            node = to_visit.pop()
            if node in removed:
                continue
            removed.add(node)
            to_visit.extend(dependents[node])

        return Dag(
            name=self.name,
            description=self.description,
            file_path=self.file_path,
            scripts={
                node: script
                for node, script in self._scripts.items()
                if node not in removed
            },
            script_dependencies={
                node: dependencies
                for node, dependencies in self._script_dependencies.items()
                if node not in removed
            },
            global_parameters=self.global_parameters,
        )

    @property
    def script_names(self) -> list[str]:
        """Return a list of names for all scripts used in pipeline."""
        return list(self._scripts.keys())

    @classmethod
    def _from_dict(
        cls, dag_data: dict, script_directory: Path, dag_directory: Path
    ) -> Dag:
        """Construct a DAG from a dictionary.

        Raises:
            PipelineParseError:
                - If an 'after' value is not a list
                - If a step has no associated dag or script path
                - If a step has unknown dependencies

        """
        scripts: dict[str, Script] = {}
        script_dependencies: dict[str, set[str]] = {}

        # This maps nested dags to their leaf nodes (so these can be used as
        # dependencies for steps dependent on the dag as a whole)
        aliases: dict[str, set[str]] = {}

        global_parameters = {
            name: Parameter(name, default)
            for name, default in dag_data.get("parameters", {}).items()
        }

        for name, specification in dag_data.get("steps", {}).items():
            after = specification.get("after", [])
            if not isinstance(after, list):
                raise PipelineParseError(
                    f"'after' lines should be lists: {after}",
                    dag_data.get("file_path", "unknown_path"),
                )

            after = set(after)

            if "dag" in specification:
                # Flatten nested DAG
                sub_dag = cls.from_toml(
                    dag_directory / specification["dag"],
                    script_directory,
                    dag_directory,
                )
                # Append a prefix to help prevent naming collisions
                prefix = f"{name}_"
                depended_on = {
                    dependency
                    for dependencies in sub_dag._script_dependencies.values()
                    for dependency in dependencies
                }
                global_parameters.update(sub_dag.global_parameters)
                for (
                    node,
                    node_dependencies,
                ) in sub_dag._script_dependencies.items():
                    prefixed_node = prefix + node
                    scripts[prefixed_node] = replace(
                        sub_dag._scripts[node], name=prefixed_node
                    )
                    script_dependencies[prefixed_node] = (
                        {
                            prefix + dependency
                            for dependency in node_dependencies
                        }
                        if node_dependencies
                        else set(after)
                    )

                aliases[name] = {
                    prefix + node
                    for node in sub_dag._script_dependencies
                    if node not in depended_on
                }
                continue

            if "path" not in specification:
                raise PipelineParseError(
                    f"Step {name!r} needs a 'path' or a 'dag'",
                    dag_data.get("file_path", "unknown_path"),
                )

            full_script_path: Path = (
                script_directory.resolve() / specification["path"]
            )
            if not full_script_path.exists():
                # We only print a warning here as this isn't really the user's
                # fault. It is more likely that the pipeline file was written
                # poorly and so a warning helps the user with raising an issue.
                tell(
                    f"WARNING: {full_script_path} does not exist!",
                    ANSIColors.YELLOW,
                )

            scripts[name] = Script(
                name=name,
                path=full_script_path,
                description=specification.get("description", ""),
                requires={
                    name: Requirement(name, instructions)
                    for name, instructions in specification.get(
                        "requires", {}
                    ).items()
                },
                parameters={
                    name: Parameter(name, value)
                    for name, value in specification.get(
                        "parameters", {}
                    ).items()
                },
            )
            script_dependencies[name] = after

        unknown_dependencies = {
            dependency
            for dependencies in script_dependencies.values()
            for dependency in dependencies
        } - script_dependencies.keys()
        if unknown_dependencies:
            raise PipelineParseError(
                f"Unknown dependencies: {sorted(unknown_dependencies)}",
                dag_data.get("file_path", "unknown_path"),
            )

        for node, node_dependencies in script_dependencies.items():
            expanded: set[str] = set()
            for dependency in node_dependencies:
                expanded |= aliases.get(dependency, {dependency})
            script_dependencies[node] = expanded
            scripts[node].dependencies = [
                scripts[dependency] for dependency in sorted(expanded)
            ]

        return cls(
            name=dag_data.get("name", "unnamed_pipeline"),
            description=dag_data.get("description", ""),
            file_path=dag_data.get("file_path", "unknown_path"),
            scripts=scripts,
            script_dependencies=script_dependencies,
            global_parameters=global_parameters,
        )
