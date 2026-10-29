"""Generation of directed acyclic graphs describing pipelines."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from functools import cached_property
from graphlib import CycleError, TopologicalSorter
from pathlib import Path


@dataclass
class Parameter:
    """Represents a configuration parameter (such as a file path)."""

    """The name of the parameter (to put into the config file)."""
    name: str

    """The default value used for the parameter."""
    default: str | int | bool | list[str] | list[int]


@dataclass
class Script:
    """Represents a script with associated information."""

    """Name of script."""
    name: str

    """Absolute path to the script."""
    path: Path

    """What the script attempts to do."""
    description: str

    """Configuration parameters needed."""
    parameters: dict[str, Parameter] = field(default_factory=dict)

    """File dependencies (for example, a reference genome)."""
    requires: list[str] = field(default_factory=list)


Step = tuple[Script, ...]


class Dag:
    """A directed acyclic graph describing a pipeline."""

    def __init__(
        self,
        name: str,
        description: str,
        scripts: dict[str, Script],
        script_dependencies: dict[str, set[str]],
        global_parameters: list[Parameter],
    ) -> None:
        """Initialise the instance."""
        self._name = name
        self._description = description
        self._scripts = scripts
        self._script_dependencies = script_dependencies
        self._global_parameters = global_parameters

    def __repr__(self) -> str:
        """Return representation of the pipeline."""
        return f"{self._name}: {self._description}"

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
            requires = ["https://www.example.com/reference"]
            after = ["read"]
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
        return cls._from_dict(data, script_directory, dag_directory)

    @cached_property
    def steps(self) -> list[Step]:
        """Layers of scripts that can be ran in parallel.

        Raises:
            RuntimeError: If there is a cycle in the pipeline

        """
        sorter = TopologicalSorter(self._script_dependencies)
        try:
            sorter.prepare()
        except CycleError as exc:
            raise RuntimeError("There is a cycle in your pipeline") from exc
        layers: list[Step] = []
        while sorter.is_active():
            ready = sorter.get_ready()
            layers.append(tuple(self._scripts[n] for n in sorted(ready)))
            sorter.done(*ready)
        return layers

    def print_diagram(self) -> None:
        """Print the pipeline top-down as layers of boxes."""

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
        print(self._name.center(canvas_width))
        print("-" * canvas_width)
        print(self._description.center(canvas_width))
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
            name=self._name,
            description=self._description,
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
            global_parameters=self._global_parameters,
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
            ValueError:
                - If a step has no associated dag or script path
                - If a step has unknown dependencies

        """
        scripts: dict[str, Script] = {}
        script_dependencies: dict[str, set[str]] = {}

        # This maps nested dags to their leaf nodes (so these can be used as
        # dependencies for steps dependent on the dag as a whole)
        aliases: dict[str, set[str]] = {}

        global_parameters = dag_data.get("parameters", [])

        for name, specification in dag_data.get("steps", {}).items():
            after = set(specification.get("after", []))

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
                raise ValueError(f"Step {name!r} needs a 'path' or a 'dag'")

            full_script_path: Path = (
                script_directory.resolve() / specification["path"]
            )
            if not full_script_path.exists():
                print(f"WARNING: {full_script_path} does not exist!")

            scripts[name] = Script(
                name=name,
                path=full_script_path,
                description=specification.get("description", ""),
                requires=specification.get("requires", []),
                parameters={
                    name: Parameter(name, value)
                    for name, value in specification.get(
                        "parameters", {}
                    ).items()
                },
            )
            script_dependencies[name] = after

        for node, node_dependencies in script_dependencies.items():
            expanded: set[str] = set()
            for dependency in node_dependencies:
                expanded |= aliases.get(dependency, {dependency})
            script_dependencies[node] = expanded

        unknown_dependencies = {
            dependency
            for dependencies in script_dependencies.values()
            for dependency in dependencies
        } - script_dependencies.keys()
        if unknown_dependencies:
            raise ValueError(
                f"Unknown dependencies: {sorted(unknown_dependencies)}"
            )

        return cls(
            name=dag_data.get("name", "unnamed_pipeline"),
            description=dag_data.get("description", ""),
            scripts=scripts,
            script_dependencies=script_dependencies,
            global_parameters=global_parameters,
        )
