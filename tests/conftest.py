"""Shared fixtures for the unit tests."""

from collections.abc import Callable, Iterable
from pathlib import Path

import pytest

from pipeline_wizard.dag import Dag


@pytest.fixture
def feed_input(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Iterable[str]], None]:
    """Provide a function that queues up answers for stdin prompts."""

    def feed(answers: Iterable[str]) -> None:
        iterator = iter(answers)
        monkeypatch.setattr(
            "builtins.input", lambda _prompt="": next(iterator)
        )

    return feed


@pytest.fixture
def make_dag(tmp_path: Path) -> Callable[..., Dag]:
    """Provide a function that builds a Dag from toml text.

    Extra toml files (for nested dags) can be given as `{name: text}`.
    """

    def make(toml_text: str, extra_files: dict[str, str] | None = None) -> Dag:
        for file_name, text in (extra_files or {}).items():
            (tmp_path / file_name).write_text(text)
        pipeline = tmp_path / "pipeline.toml"
        pipeline.write_text(toml_text)
        return Dag.from_toml(pipeline, tmp_path, tmp_path)

    return make
