"""Unit tests for user prompts."""

from collections.abc import Callable, Iterable
from pathlib import Path

import pytest

from pipeline_wizard.dag import Parameter, Requirement
from pipeline_wizard.prompts import (
    TODO,
    prompt_for_parameter_value,
    prompt_for_requirement_path,
)

Feed = Callable[[Iterable[str]], None]


@pytest.mark.parametrize(
    ("default", "answers", "expected"),
    [
        (["v1", "v2"], ["2"], "v2"),
        ([10, 20], ["1"], 10),
        (True, ["no"], False),
        (False, ["yes"], True),
        (5, ["8"], 8),
        (5, [""], 5),
        ("abc", ["xyz"], "xyz"),
        ("abc", [""], "abc"),
    ],
)
def test_prompts_for_parameter_value(
    feed_input: Feed,
    default: str | int | bool | list,
    answers: list[str],
    expected: str | int | bool,
) -> None:
    """Should ask for a value appropriate to the type of the default.

    Given:
        A parameter whose default is a list, bool, int or str.
    When:
        The user answers (or accepts the default).
    Then:
        The returned value is the picked option or the typed value, coerced to
        the type of the default.

    """
    feed_input(answers)

    assert prompt_for_parameter_value(Parameter("p", default)) == expected


def test_returns_existing_path_the_user_has(
    feed_input: Feed, tmp_path: Path
) -> None:
    """Should return the path of a file the user already has.

    Given:
        The user says they have the file and gives an existing path.
    When:
        The requirement is prompted for.
    Then:
        The resolved path is returned.

    """
    existing = tmp_path / "ref.fa"
    existing.write_text("x")
    feed_input(["yes", str(existing)])

    result = prompt_for_requirement_path(Requirement("ref", "instructions"))

    assert result == existing.resolve()


def test_asks_again_if_given_path_does_not_exist(
    feed_input: Feed, tmp_path: Path
) -> None:
    """Should re-ask until an existing path is given.

    Given:
        The user gives a missing path, then confirms and gives a real one.
    When:
        The requirement is prompted for.
    Then:
        The real path is returned.

    """
    existing = tmp_path / "ref.fa"
    existing.write_text("x")
    feed_input(["yes", str(tmp_path / "nope"), "yes", str(existing)])

    result = prompt_for_requirement_path(Requirement("ref", "instructions"))

    assert result == existing.resolve()


def test_shows_instructions_when_user_lacks_file(
    feed_input: Feed, capsys: pytest.CaptureFixture[str]
) -> None:
    """Should show non URL instructions when the user lacks the file.

    Given:
        A requirement with plain text instructions and no file.
    When:
        The requirement is prompted for.
    Then:
        The instructions are printed.

    """
    feed_input(["no"])

    prompt_for_requirement_path(Requirement("ref", "ask the lab manager"))

    assert "ask the lab manager" in capsys.readouterr().out


def test_downloads_requirement_from_url(
    feed_input: Feed,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Should download the requirement when the user asks for it.

    Given:
        A URL requirement, no local file and a download destination.
    When:
        The requirement is prompted for.
    Then:
        The URL is downloaded and the downloaded path returned.

    """
    calls: list[tuple[str, Path]] = []

    def fake_download(url: str, destination: Path, name: str) -> Path:
        calls.append((url, destination))
        return destination

    monkeypatch.setattr("pipeline_wizard.prompts.download_file", fake_download)
    target = tmp_path / "ref.fa"
    feed_input(["no", "yes", str(target)])

    result = prompt_for_requirement_path(
        Requirement("ref", "https://example.com/ref.fa")
    )

    assert result == target
    assert calls == [("https://example.com/ref.fa", target)]


def test_declining_download_returns_placeholder_path(
    feed_input: Feed,
) -> None:
    """Should not download when the user declines.

    Given:
        A URL requirement where the user has no file and declines download.
    When:
        The requirement is prompted for.
    Then:
        The placeholder path (current directory) is returned.

    """
    feed_input(["no", "no"])

    result = prompt_for_requirement_path(
        Requirement("ref", "https://example.com/ref.fa")
    )

    assert result == TODO
