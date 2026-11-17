"""Unit tests for the configuration file writer."""

from pathlib import Path

import pytest

from pipeline_wizard.config_builder import ConfigBuilder
from pipeline_wizard.dag import Dag
from pipeline_wizard.script import Parameter, Requirement


def _written(builder: ConfigBuilder, tmp_path: Path) -> list[str]:
    out = tmp_path / "config.sh"
    builder.write_config_file(out)
    return out.read_text().splitlines()


@pytest.fixture()
def config_builder() -> ConfigBuilder:
    """Build a dummy config builder with minimal pipeline."""
    dummy_pipeline = Dag.__new__(Dag)
    dummy_pipeline.name = "pipeline name"
    dummy_pipeline.version = "v0.1.0"

    return ConfigBuilder(dummy_pipeline)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("text", 'export NAME="text"'),
        (7, "export NAME=7"),
        (True, "export NAME=true"),
        (False, "export NAME=false"),
    ],
)
def test_writes_parameter_as_export(
    tmp_path: Path,
    config_builder: ConfigBuilder,
    value: str | int | bool,
    expected: str,
) -> None:
    """Should write parameters as shell exports with the right literal.

    Given:
        A parameter and a string, int or bool value.
    When:
        The config file is written.
    Then:
        The line is an upper case export (strings quoted, bools TRUE/FALSE).

    """
    config_builder.add_parameter_value_pair(Parameter("NAME", ""), value)

    for line in [expected]:
        assert line in _written(config_builder, tmp_path)


def test_writes_requirement_path(
    tmp_path: Path,
    config_builder: ConfigBuilder,
) -> None:
    """Should write requirements as quoted upper case exports.

    Given:
        A requirement and a path.
    When:
        The config file is written.
    Then:
        The path is exported under the upper cased requirement name.

    """
    config_builder.add_requirement_path_pair(
        Requirement("REF", "how to get"), Path("/data/ref.fa")
    )

    assert 'export REF="/data/ref.fa"' in _written(config_builder, tmp_path)


def test_ignores_repeated_parameter(
    tmp_path: Path,
    config_builder: ConfigBuilder,
) -> None:
    """Should only keep the first value for a repeated parameter.

    Given:
        The same parameter added twice with different values.
    When:
        The config file is written.
    Then:
        Only the first value is present.

    """
    config_builder.add_parameter_value_pair(Parameter("N", 1), 1)
    config_builder.add_parameter_value_pair(Parameter("N", 1), 2)

    assert "export N=1" in _written(config_builder, tmp_path)


def test_ignores_repeated_requirement(
    tmp_path: Path,
    config_builder: ConfigBuilder,
) -> None:
    """Should only keep the first path for a repeated requirement.

    Given:
        The same requirement added twice.
    When:
        The config file is written.
    Then:
        Only one line is present.

    """
    requirement = Requirement("REF", "x")
    config_builder.add_requirement_path_pair(requirement, Path("/a"))
    config_builder.add_requirement_path_pair(requirement, Path("/b"))

    assert 'export REF="/a"' in _written(config_builder, tmp_path)


def test_tracks_added_names(config_builder: ConfigBuilder) -> None:
    """Should expose which parameters and requirements have been added.

    Given:
        One parameter and one requirement added.
    When:
        The tracked names are inspected.
    Then:
        They contain the (original case) names.

    """
    config_builder.add_parameter_value_pair(Parameter("P", 1), 1)
    config_builder.add_requirement_path_pair(Requirement("R", "x"), Path("/r"))

    assert "P" in config_builder.parameters
    assert "R" in config_builder.requirements


def test_write_fails_for_unwritable_path(
    tmp_path: Path, config_builder: ConfigBuilder
) -> None:
    """Should raise OSError when the file can't be written.

    Given:
        An output path inside a directory that doesn't exist.
    When:
        The config file is written.
    Then:
        An OSError is raised.

    """
    with pytest.raises(OSError):  # noqa: PT011
        config_builder.write_config_file(tmp_path / "missing" / "c.sh")


def test_escapes_shell_metacharacters(
    tmp_path: Path, config_builder: ConfigBuilder
) -> None:
    """Should write values that are safe when sourced by bash.

    Given:
        A string value containing quotes and a command substitution.
    When:
        The config file is written and sourced by bash.
    Then:
        The variable holds the literal original text.

    """
    import subprocess

    value = 'he said "hi" $HOME `id`'
    print(config_builder.add_parameter_value_pair(Parameter("M", ""), value))
    out = tmp_path / "config.sh"
    config_builder.write_config_file(out)

    result = subprocess.run(
        ["bash", "-c", f'source "{out}"; printf %s "$M"'],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.stdout == value
