"""Unit tests for the configuration file writer."""

from pathlib import Path

import pytest

from pipeline_wizard.config_builder import ConfigBuilder
from pipeline_wizard.dag import Parameter, Requirement


def _written(builder: ConfigBuilder, tmp_path: Path) -> list[str]:
    out = tmp_path / "config.sh"
    builder.write_config_file(out)
    return out.read_text().splitlines()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("text", 'export NAME="text"'),
        (7, "export NAME=7"),
        (True, "export NAME=TRUE"),
        (False, "export NAME=FALSE"),
    ],
)
def test_writes_parameter_as_export(
    tmp_path: Path, value: str | int | bool, expected: str
) -> None:
    """Should write parameters as shell exports with the right literal.

    Given:
        A parameter and a string, int or bool value.
    When:
        The config file is written.
    Then:
        The line is an upper case export (strings quoted, bools TRUE/FALSE).

    """
    builder = ConfigBuilder()
    builder.add_parameter_value_pair(Parameter("name", ""), value)

    assert _written(builder, tmp_path) == [expected]


def test_writes_requirement_path(tmp_path: Path) -> None:
    """Should write requirements as quoted upper case exports.

    Given:
        A requirement and a path.
    When:
        The config file is written.
    Then:
        The path is exported under the upper cased requirement name.

    """
    builder = ConfigBuilder()
    builder.add_requirement_path_pair(
        Requirement("ref", "how to get"), Path("/data/ref.fa")
    )

    assert _written(builder, tmp_path) == ['export REF="/data/ref.fa"']


def test_ignores_repeated_parameter(tmp_path: Path) -> None:
    """Should only keep the first value for a repeated parameter.

    Given:
        The same parameter added twice with different values.
    When:
        The config file is written.
    Then:
        Only the first value is present.

    """
    builder = ConfigBuilder()
    builder.add_parameter_value_pair(Parameter("n", 1), 1)
    builder.add_parameter_value_pair(Parameter("n", 1), 2)

    assert _written(builder, tmp_path) == ["export N=1"]


def test_ignores_repeated_requirement(tmp_path: Path) -> None:
    """Should only keep the first path for a repeated requirement.

    Given:
        The same requirement added twice.
    When:
        The config file is written.
    Then:
        Only one line is present.

    """
    builder = ConfigBuilder()
    requirement = Requirement("ref", "x")
    builder.add_requirement_path_pair(requirement, Path("/a"))
    builder.add_requirement_path_pair(requirement, Path("/b"))

    assert _written(builder, tmp_path) == ['export REF="/a"']


def test_tracks_added_names() -> None:
    """Should expose which parameters and requirements have been added.

    Given:
        One parameter and one requirement added.
    When:
        The tracked names are inspected.
    Then:
        They contain the (original case) names.

    """
    builder = ConfigBuilder()
    builder.add_parameter_value_pair(Parameter("p", 1), 1)
    builder.add_requirement_path_pair(Requirement("r", "x"), Path("/r"))

    assert "p" in builder.parameters
    assert "r" in builder.requirements


def test_write_fails_for_unwritable_path(tmp_path: Path) -> None:
    """Should raise OSError when the file can't be written.

    Given:
        An output path inside a directory that doesn't exist.
    When:
        The config file is written.
    Then:
        An OSError is raised.

    """
    with pytest.raises(OSError):  # noqa: PT011
        ConfigBuilder().write_config_file(tmp_path / "missing" / "c.sh")


def test_escapes_shell_metacharacters(tmp_path: Path) -> None:
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
    builder = ConfigBuilder()
    print(builder.add_parameter_value_pair(Parameter("m", ""), value))
    out = tmp_path / "config.sh"
    builder.write_config_file(out)

    result = subprocess.run(
        ["bash", "-c", f'source "{out}"; printf %s "$M"'],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.stdout == value
