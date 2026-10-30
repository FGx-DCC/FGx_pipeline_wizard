"""Unit tests for pipeline dag construction and manipulation."""

from collections.abc import Callable
from pathlib import Path

import pytest

from pipeline_wizard.dag import Dag
from pipeline_wizard.exceptions import NotADagError, PipelineParseError

CHAIN = """
name = "Chain"
description = "a then b then c"
[parameters]
out = "/out"
[steps.a]
path = "a.sh"
[steps.b]
path = "b.sh"
after = ["a"]
[steps.b.parameters]
n = 5
[steps.b.requires]
ref = "https://example.com/ref"
[steps.c]
path = "c.sh"
after = ["b"]
"""

DIAMOND = """
[steps.a]
path = "a.sh"
[steps.b]
path = "b.sh"
after = ["a"]
[steps.c]
path = "c.sh"
after = ["a"]
[steps.d]
path = "d.sh"
after = ["b", "c"]
"""


def _names(dag: Dag) -> list[list[str]]:
    return [[script.name for script in step] for step in dag.steps]


def test_reads_pipeline_metadata(make_dag: Callable[..., Dag]) -> None:
    """Should expose the name, description and title from the toml.

    Given:
        A pipeline toml with a name and description.
    When:
        The dag is read.
    Then:
        The name, description and title match the toml.

    """
    dag = make_dag(CHAIN)

    assert dag.name == "Chain"
    assert dag.description == "a then b then c"
    assert dag.title() == "Chain: a then b then c"


def test_uses_defaults_for_missing_metadata(
    make_dag: Callable[..., Dag],
) -> None:
    """Should fall back to default metadata.

    Given:
        A pipeline toml without a name or description.
    When:
        The dag is read.
    Then:
        The name and description are set to some string.

    """
    dag = make_dag('[steps.a]\npath = "a.sh"\n')

    assert isinstance(dag.name, str)
    assert isinstance(dag.description, str)


def test_groups_scripts_into_parallel_layers(
    make_dag: Callable[..., Dag],
) -> None:
    """Should group scripts that can run in parallel into the same step.

    Given:
        A diamond shaped pipeline (a -> b, c -> d).
    When:
        The steps are requested.
    Then:
        There are three layers, with b and c sharing the middle one.

    """
    dag = make_dag(DIAMOND)

    assert _names(dag) == [["a"], ["b", "c"], ["d"]]


def test_script_holds_parameters_requirements_and_path(
    make_dag: Callable[..., Dag], tmp_path: Path
) -> None:
    """Should attach parameters, requirements and paths to scripts.

    Given:
        A step with parameters and requirements.
    When:
        The dag is read.
    Then:
        The script has them, with an absolute path under the scripts directory.

    """
    dag = make_dag(CHAIN)
    script = dag.steps[1][0]

    assert script.parameters["n"].default == 5
    assert script.requires["ref"].instructions == "https://example.com/ref"
    assert script.path == tmp_path.resolve() / "b.sh"


def test_script_lists_its_dependencies(make_dag: Callable[..., Dag]) -> None:
    """Should list the scripts a script must wait for.

    Given:
        A pipeline where d depends on b and c.
    When:
        The dag is read.
    Then:
        The dependencies of d are b and c.

    """
    dag = make_dag(DIAMOND)
    final = dag.steps[-1][0]

    assert sorted(s.name for s in final.dependencies) == ["b", "c"]


def test_reads_global_parameters(make_dag: Callable[..., Dag]) -> None:
    """Should expose pipeline wide parameters.

    Given:
        A toml with a [parameters] section.
    When:
        The dag is read.
    Then:
        The global parameters hold the defaults.

    """
    dag = make_dag(CHAIN)

    assert dag.global_parameters["out"].default == "/out"


def test_lists_script_names(make_dag: Callable[..., Dag]) -> None:
    """Should list every script name.

    Given:
        A three script pipeline.
    When:
        The script names are requested.
    Then:
        All three are returned.

    """
    dag = make_dag(CHAIN)

    assert sorted(dag.script_names) == ["a", "b", "c"]


def test_prune_removes_script_and_dependents(
    make_dag: Callable[..., Dag],
) -> None:
    """Should remove a script along with everything downstream.

    Given:
        A diamond pipeline.
    When:
        Script b is pruned.
    Then:
        b and d are removed, a and c remain.

    """
    dag = make_dag(DIAMOND)

    pruned = dag.prune("b")

    assert sorted(pruned.script_names) == ["a", "c"]


def test_prune_does_not_modify_original(make_dag: Callable[..., Dag]) -> None:
    """Should leave the original dag untouched.

    Given:
        A pipeline.
    When:
        A script is pruned.
    Then:
        The original still has all of its scripts.

    """
    dag = make_dag(CHAIN)

    dag.prune("a")

    assert sorted(dag.script_names) == ["a", "b", "c"]


def test_prune_everything_gives_empty_pipeline(
    make_dag: Callable[..., Dag],
) -> None:
    """Should allow pruning down to nothing.

    Given:
        A chain pipeline.
    When:
        The first script is pruned.
    Then:
        No scripts or steps remain.

    """
    pruned = make_dag(CHAIN).prune("a")

    assert pruned.script_names == []
    assert pruned.steps == []
    assert pruned.empty


def test_prune_unknown_script_raises(make_dag: Callable[..., Dag]) -> None:
    """Should refuse to prune a script that isn't in the pipeline.

    Given:
        A pipeline.
    When:
        A name not in the pipeline is pruned.
    Then:
        A ValueError is raised.

    """
    with pytest.raises(ValueError, match="not a script"):
        make_dag(CHAIN).prune("nope")


def test_nested_dag_is_flattened_with_prefix(
    make_dag: Callable[..., Dag],
) -> None:
    """Should flatten nested dags and prefix their script names.

    Given:
        A pipeline embedding another toml after a step.
    When:
        The dag is read.
    Then:
        Nested scripts are prefixed with the step name and run after it, and
        the nested pipeline's parameters become global.

    """
    nested = (
        '[parameters]\nreport_dir = "/r"\n'
        '[steps.x]\npath = "x.sh"\n'
        '[steps.y]\npath = "y.sh"\nafter = ["x"]\n'
    )
    top = (
        '[steps.a]\npath = "a.sh"\n'
        '[steps.rep]\ndag = "nested.toml"\nafter = ["a"]\n'
    )

    dag = make_dag(top, {"nested.toml": nested})

    assert _names(dag) == [["a"], ["rep_x"], ["rep_y"]]
    assert "report_dir" in dag.global_parameters


def test_step_after_nested_dag_waits_for_its_final_scripts(
    make_dag: Callable[..., Dag],
) -> None:
    """Should make steps depending on a nested dag wait for all its leaves.

    Given:
        A step that comes after a nested dag.
    When:
        The dag is read.
    Then:
        The step is in a later layer than the nested dag's last script.

    """
    nested = (
        '[steps.x]\npath = "x.sh"\n[steps.y]\npath = "y.sh"\nafter = ["x"]\n'
    )
    top = (
        '[steps.rep]\ndag = "nested.toml"\n'
        '[steps.z]\npath = "z.sh"\nafter = ["rep"]\n'
    )

    dag = make_dag(top, {"nested.toml": nested})

    assert _names(dag) == [["rep_x"], ["rep_y"], ["z"]]


@pytest.mark.parametrize(
    ("toml_text", "message"),
    [
        ('[steps.a]\ndescription = "no path"\n', "needs a 'path'"),
        pytest.param(
            '[steps.a]\npath = "a.sh"\nafter = ["ghost"]\n',
            "Unknown dependencies",
        ),
        ('[steps.a]\npath = "a.sh"\nafter = "b"\n', "should be lists"),
    ],
)
def test_invalid_pipeline_raises_error(
    make_dag: Callable[..., Dag], toml_text: str, message: str
) -> None:
    """Should reject malformed pipeline definitions.

    Given:
        A toml with a missing path, an unknown dependency or a non list after.
    When:
        The dag is read.
    Then:
        A PipelineParseError describing the problem is raised.

    """
    with pytest.raises(PipelineParseError, match=message):
        make_dag(toml_text)


def test_cycle_raises_error(make_dag: Callable[..., Dag]) -> None:
    """Should refuse to order a pipeline containing a cycle.

    Given:
        Two scripts that depend on each other.
    When:
        The steps are requested.
    Then:
        A NotADagError is raised.

    """
    dag = make_dag(
        '[steps.a]\npath = "a.sh"\nafter = ["b"]\n'
        '[steps.b]\npath = "b.sh"\nafter = ["a"]\n'
    )

    with pytest.raises(NotADagError, match="cycle"):
        _ = dag.steps


def test_missing_script_file_warns(
    make_dag: Callable[..., Dag], capsys: pytest.CaptureFixture[str]
) -> None:
    """Should warn (not fail) when a script file doesn't exist.

    Given:
        A pipeline pointing to a script that is not on disk.
    When:
        The dag is read.
    Then:
        A warning mentioning the path is printed.

    """
    make_dag('[steps.a]\npath = "missing.sh"\n')

    assert "does not exist" in capsys.readouterr().out


def test_print_diagram_shows_every_script(
    make_dag: Callable[..., Dag], capsys: pytest.CaptureFixture[str]
) -> None:
    """Should print each script name in the diagram.

    Given:
        A diamond pipeline.
    When:
        The diagram is printed.
    Then:
        Every script name appears in the output.

    """
    make_dag(DIAMOND).print_diagram()

    output = capsys.readouterr().out
    for name in "abcd":
        assert f" {name} " in output


def test_print_diagram_of_empty_pipeline(
    make_dag: Callable[..., Dag], capsys: pytest.CaptureFixture[str]
) -> None:
    """Should say when there is nothing to draw.

    Given:
        A pipeline with every script pruned.
    When:
        The diagram is printed.
    Then:
        A message saying the pipeline is empty is shown.

    """
    make_dag(CHAIN).prune("a").print_diagram()

    assert "empty" in capsys.readouterr().out
