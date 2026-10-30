"""Unit tests for terminal interaction helpers."""

from collections.abc import Callable, Iterable

import pytest

from pipeline_wizard.wizard import (
    ask,
    ask_bool,
)

Feed = Callable[[Iterable[str]], None]


def test_ask_coerces_to_return_type(feed_input: Feed) -> None:
    """Should convert input to the requested type.

    Given:
        The user types '42'.
    When:
        ask is called for an int, a str and a float.
    Then:
        Each value has the requested type.

    """
    feed_input(["42", "42", "42"])

    assert ask("q", return_type=int) == 42
    assert ask("q", return_type=str) == "42"
    assert ask("q", return_type=float) == 42.0


def test_ask_reprompts_on_invalid_input(feed_input: Feed) -> None:
    """Should keep asking until the input can be coerced.

    Given:
        The user first types text then a number.
    When:
        An int is asked for.
    Then:
        The number is returned.

    """
    feed_input(["abc", "5"])

    assert ask("q", return_type=int) == 5


def test_ask_ignores_empty_input_without_default(feed_input: Feed) -> None:
    """Should keep asking when nothing is typed and there's no default.

    Given:
        The user hits enter and then types a value.
    When:
        ask is called without a default.
    Then:
        The typed value is returned.

    """
    feed_input(["", "7"])

    assert ask("q") == 7


def test_ask_returns_default_on_empty_input(feed_input: Feed) -> None:
    """Should return the default when nothing is typed.

    Given:
        A default and the user hitting enter.
    When:
        ask is called.
    Then:
        The default is returned.

    """
    feed_input([""])

    assert ask("q", return_type=str, default="fallback") == "fallback"


def test_ask_choices_returns_zero_based_index(feed_input: Feed) -> None:
    """Should return the index of the chosen option.

    Given:
        Three choices and the user typing '2'.
    When:
        ask is called.
    Then:
        1 is returned (zero based).

    """
    feed_input(["2"])

    assert ask("q", choices=["a", "b", "c"]) == 1


def test_ask_choices_rejects_out_of_range(feed_input: Feed) -> None:
    """Should re-ask when the choice isn't in range.

    Given:
        The user types 0, 4 then 3 for three choices.
    When:
        ask is called.
    Then:
        Index 2 is returned.

    """
    feed_input(["0", "4", "3"])

    assert ask("q", choices=["a", "b", "c"]) == 2


def test_ask_choices_default_is_index(feed_input: Feed) -> None:
    """Should return the default index on empty input.

    Given:
        Choices with default index 1.
    When:
        The user hits enter.
    Then:
        1 is returned.

    """
    feed_input([""])

    assert ask("q", choices=["a", "b"], default=1) == 1


def test_ask_rejects_default_outside_choices() -> None:
    """Should refuse an invalid default index.

    Given:
        Two choices and a default of 5.
    When:
        ask is called.
    Then:
        A ValueError is raised.

    """
    with pytest.raises(ValueError, match="Default"):
        ask("q", choices=["a", "b"], default=5)


def test_ask_exits_on_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    """Should exit cleanly when the user sends EOF.

    Given:
        stdin raising EOFError.
    When:
        ask is called.
    Then:
        SystemExit with code 0 is raised.

    """

    def raise_eof(_prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)

    with pytest.raises(SystemExit) as exc_info:
        ask("q")

    assert exc_info.value.code == 0


def test_ask_bool_reprompts_on_unknown_answer(feed_input: Feed) -> None:
    """Should keep asking until it gets an understandable answer.

    Given:
        The user types 'maybe' then 'yes'.
    When:
        ask_bool is called.
    Then:
        True is returned.

    """
    feed_input(["this-is-an-unknown-answer", "yes"])

    assert ask_bool("q") is True
