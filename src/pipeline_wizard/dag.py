"""Generation of directed acyclic graphs describing pipelines."""

from __future__ import annotations

import tomllib
from dataclasses import replace
from functools import cached_property
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

from pipeline_wizard.directive_parser import read_directives
from pipeline_wizard.directives import Directives
from pipeline_wizard.exceptions import (
    NotADagError,
    NotUpperError,
    PipelineParseError,
)
from pipeline_wizard.script import Parameter, Requirement, Script
from pipeline_wizard.types import AbsolutePath
from pipeline_wizard.wizard import ANSIColors, tell

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
        cls, path: Path, script_directory: Path, pipeline_directory: Path
    ) -> Dag:
        """Read DAG from a toml file.

        View the README at repository root for an example of the toml format
        expected here.

        """
        with path.open("rb") as dag_toml:
            data = tomllib.load(dag_toml)

        return cls._from_dict(data, path, script_directory, pipeline_directory)

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
    def _from_dict(  # noqa: C901
        cls,
        dag_data: dict,
        dag_path: Path,
        script_directory: Path,
        pipeline_directory: Path,
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

        try:
            global_parameters = {
                name: Parameter(name, default)
                for name, default in dag_data.get("parameters", {}).items()
            }
        except NotUpperError as exc:
            raise PipelineParseError(f"{exc}", dag_path) from exc

        for name, specification in dag_data.get("steps", {}).items():
            after = specification.get("after", [])
            if not isinstance(after, list):
                raise PipelineParseError(
                    f"'after' lines should be lists: {after}",
                    dag_path,
                )

            after = set(after)

            if "dag" in specification:
                # Flatten nested DAG
                sub_dag = cls.from_toml(
                    pipeline_directory / specification["dag"],
                    script_directory,
                    pipeline_directory,
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
                    dag_path,
                )

            full_script_path: AbsolutePath = (
                AbsolutePath(script_directory) / specification["path"]
            )
            if not full_script_path.exists():
                # We only print a warning here as this isn't really the user's
                # fault. It is more likely that the pipeline file was written
                # poorly and so a warning helps the user with raising an issue.
                tell(
                    f"WARNING: {full_script_path} does not exist!",
                    ANSIColors.YELLOW,
                )

            try:
                if full_script_path.exists():
                    directives = read_directives(full_script_path)
                else:
                    directives = Directives()
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
                    directives=directives,
                )
            except NotUpperError as exc:
                raise PipelineParseError(f"{exc}", dag_path) from exc
            script_dependencies[name] = after

        known_names = script_dependencies.keys() | aliases.keys()
        unknown_dependencies = {
            dependency
            for dependencies in script_dependencies.values()
            for dependency in dependencies
        } - known_names
        if unknown_dependencies:
            raise PipelineParseError(
                f"Unknown dependencies: {sorted(unknown_dependencies)}",
                dag_path,
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
            file_path=dag_path,
            scripts=scripts,
            script_dependencies=script_dependencies,
            global_parameters=global_parameters,
        )
