#!/bin/env python3

import sys
from inspect import cleandoc
from typing import Any, NoReturn, overload


class ANSIColors:
    """Define ANSI escape codes.

    Taken from stdlib `_colorize.py`. This is just a subset of that class and
    it isn't imported directly here as it is not in a public module as of
    2026/09/28.

    """

    RESET = "\x1b[0m"

    BLACK = "\x1b[30m"
    BLUE = "\x1b[34m"
    CYAN = "\x1b[36m"
    GREEN = "\x1b[32m"
    GREY = "\x1b[90m"
    MAGENTA = "\x1b[35m"
    RED = "\x1b[31m"
    WHITE = "\x1b[37m"
    YELLOW = "\x1b[33m"


def tell(message: str) -> None:
    """Print formatted text to the terminal.

    This is required as many messages to be sent to the user by the wizard will
    be very long. Formatting such a string in code typically is in contention
    with formatting the string in the terminal. The reason for this is that
    we wish for strings to fit inside a certain column limit (as it is easier
    to edit this way). To accomplish this, you'd use a docstring (like this
    one). However, such use of a docstring isn't good enough as the indent
    imposed by python will be interpreted as literal whitespace in the printed
    text. The solution is either: deindent the inner text of the docstring
    (which is yuck) or use `inspect.cleandoc` (what this function does).

    Args:
        message:
            The text to print to the terminal.

    """
    print(cleandoc(message))


def exit_with_message(message: str, exit_code: int = 1) -> NoReturn:
    """Print message and exit code execution.

    The primary purpose of this function is to exit when an unrecoverable
    error occurs and it is better to just stop. The most common usage would be
    some file cannot be read (which the command will have no means of fixing).

    Args:
        message:
            The text to print to the terminal, this will be formatted red if
            `exit_code` is non zero (default).
        exit_code:
            The code to send to `sys.exit()`.

    """
    if exit_code != 0:
        message = ANSIColors.RED + message + ANSIColors.RESET
    tell(message)
    sys.exit(exit_code)


@overload
def ask(message: str, *, choices: list[str]) -> int: ...


@overload
def ask[T: (int, str, float)](message: str, *, return_type: type[T]) -> T: ...


@overload
def ask(message: str) -> int: ...


def ask(
    message: str,
    choices: list[str] | None = None,
    return_type: type[int] | type[str] | type[float] = int,
) -> Any:
    """Tell then obtain an answer from stdin.

    Sending and EOF marker will terminate the program, mimicking REPL behaviour
    (though this is done at a python level, rather than at C level).

    Args:
        message:
            The text to print to the terminal.
        choices:
            An optional list of choices (user only needs to type 1-x). These
            will be enumerated.
        return_type:
            The type to coerse user input to.

    Returns:
        The coerced value from the user input. If `choices` is given, the
        index of the choices is returned.

    Note:
        `ask` has three different return types depending on how it's called,
        and a single signature can't express that:

          ask("msg", return_type=str)   -> str
                    (input coerced to the requested type)

          ask("msg", choices=[...])     -> int
                    (0-based index of the chosen option)

          ask("msg")                    -> int
                    (return_type defaults to int)

        Without overloads, the return annotation has to be `T | int`, which
        forces every caller to narrow or `# type: ignore`, even when they asked
        for a `str`. The overloads below give each call shape its own precise
        return type.

        The implementation signature further down is NOT visible to callers. It
        just has to be broad enough to accept every overload, hence the
        explicit `type[int] | type[str] | ...` union and the `Any` return.

    """
    tell(message)

    if choices:
        print(
            "\n".join(
                [
                    f"  {ANSIColors.GREEN}{index}.{ANSIColors.RESET} {choice}"
                    for index, choice in enumerate(choices, 1)
                ]
            )
        )

    while True:
        try:
            user_input = input(
                f"{ANSIColors.GREEN}${ANSIColors.RESET} "
            ).strip()
            if not user_input:
                continue
            if choices:
                choice = int(user_input)
                if choice in range(1, len(choices) + 1):
                    return choice - 1  # back to 0-based indexing
                tell(f"Your answer must be between 1 and {len(choices)}")
                continue
            return return_type(user_input)
        except (ValueError, TypeError):
            tell("Invalid input")
        except KeyboardInterrupt:
            print("\nKeyboardInterrupt")  # Matches REPL
        except EOFError:
            print()
            sys.exit(0)  # Matches REPL


def ask_optional(
    message: str,
    sentinel: str,
) -> str | None:
    """Ask, but returns None if the answer matches `sentinel`.

    This is better than using some 'defaults' approach as the type coercion
    that needs to be accounted for for `None` causes too much complexity in
    the 'ask' function.

    """
    answer = ask(message, return_type=str)
    return None if answer.strip().lower() == sentinel.lower() else answer


def ask_bool(message: str) -> bool:
    """Ask, but coerce to bool.

    This is required as coercing 'False' to `bool` gives you `True`.

    """
    truthy = {"yes", "y", "yep", "true", "1", "yes please"}
    falsey = {"no", "n", "nope", "false", "0", "no thank you", "no thanks"}
    while True:
        answer = ask(message, return_type=str)
        if answer.lower() in truthy:
            return True
        if answer.lower() in falsey:
            return False
        tell("Invalid input (try 'yes', 'no' etc.)")
