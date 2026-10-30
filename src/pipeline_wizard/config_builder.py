"""Writer for configuration file."""

from pathlib import Path

from pipeline_wizard.dag import Parameter, Requirement
from pipeline_wizard.prompts import TODO


class ConfigBuilder:
    """Config writer, module by module.

    The configuration file will be of the form::

        export PARAMETER=value
        export PARAMETER=value
        ...
        export PARAMETER=value
        ...
        export REQUIREMENT=/path/to/requirement


    All scripts will use these parameters from the environment (hence the use
    of `export`).

    """

    def __init__(self) -> None:
        """Initialise the instance."""
        self.parameters = set()
        self.requirements = set()
        self._contents = []

    def add_parameter_value_pair(
        self, parameter: Parameter, value: str | int | bool
    ) -> None:
        """Append config parameter to configuration file contents.

        Note:
            Values are not checked, this is just a writer. The caller should
            validate that values are sensible/correct (for example, checking
            that file paths exist/can be written to).

        """
        if parameter.name in self.parameters:
            return

        if isinstance(value, str):
            escaped = (
                value.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("$", "\\$")
                .replace("`", "\\`")
            )
            value = f'"{escaped}"'
        elif isinstance(value, bool):
            value = "TRUE" if value else "FALSE"

        self.parameters.add(parameter.name)
        self._contents.append(f"export {parameter.name.upper()}={value}")

    def add_requirement_path_pair(
        self, requirement: Requirement, requirement_path: Path | TODO
    ) -> None:
        """Append requirement to configuration file contents."""
        if requirement.name in self.requirements:
            return
        self.requirements.add(requirement.name)

        if requirement_path is TODO:
            self._contents.append(
                f"# Fill below using: {requirement.instructions}"
            )
            self._contents.append(f"export {requirement.name.upper()}=")
            return

        self._contents.append(
            f'export {requirement.name.upper()}="{str(requirement_path)}"'
        )

    def write_config_file(self, out_path: Path) -> None:
        """Write the contents of the run script to the path.

        Raises:
            OSError:
                If the file handle couldn't be opened to write. In such cases,
                the method should be retried with a different path.

        """
        with open(out_path, mode="w") as config_file:
            config_file.write("\n".join(self._contents))
