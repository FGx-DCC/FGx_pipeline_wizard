"""Generation of directed acyclic graphs describing pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import cached_property
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

import tomllib


@dataclass
class Parameter:
    """Represents a configuration parameter (such as a file path)."""

    """The name of the parameter (to put into the config file)."""
    name: str

    """The default value used for the parameter."""
    default: str | int


@dataclass
class Script:
    """Represents a script with associated information."""

    """Name of script."""
    name: str

    """Path should be relative to the scripts directory."""
    path: str

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
        decription: str,
        scripts: dict[str, Script],
        script_dependencies: dict[str, set[str]],
    ):
        """Initialise the instance."""
        self._name = name
        self._decription = decription
        self._scripts = scripts
        self._dependencies = script_dependencies

    @classmethod
    def from_toml(
        cls, path: Path, script_directory: Path, dag_directory: Path
    ) -> Dag:
        """Read DAG from a toml file.

        Example toml file::

            name = "Test Pipeline"
            description = "A test pipeline with read, clean and write steps"

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
        sorter = TopologicalSorter(self._dependencies)
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
        aliases: dict[str, set[str]] = {}  # nested dag -> leaf nodes

        for name, spec in dag_data.get("steps", {}).items():
            after = set(spec.get("after", []))

            if "dag" in spec:
                # Flatten nested DAG
                sub = cls.from_toml(
                    dag_directory / spec["dag"],
                    script_directory,
                    dag_directory,
                )
                # Append a prefix to help prevent naming collisions
                prefix = f"{name}_"
                depended_on = {
                    dependency
                    for dependencies in sub._dependencies.values()
                    for dependency in dependencies
                }
                for node, node_dependencies in sub._dependencies.items():
                    new_node = prefix + node
                    scripts[new_node] = replace(
                        sub._scripts[node], name=new_node
                    )
                    script_dependencies[new_node] = (
                        {
                            prefix + dependency
                            for dependency in node_dependencies
                        }
                        if node_dependencies
                        else set(after)
                    )
                aliases[name] = {
                    prefix + n
                    for n in sub._dependencies
                    if n not in depended_on
                }
                continue

            if "path" not in spec:
                raise ValueError(f"Step {name!r} needs a 'path' or a 'dag'")

            scripts[name] = Script(
                name=name,
                path=script_directory / spec["path"],
                description=spec.get("description", ""),
                requires=spec.get("requires", []),
                parameters={
                    name: Parameter(name, value)
                    for name, value in spec.get("parameters", {}).items()
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
            dag_data.get("name", "unnamed"),
            dag_data.get("description", ""),
            scripts,
            script_dependencies,
        )
