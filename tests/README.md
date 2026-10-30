# Tests

Unit tests for `pipeline_wizard`, written with [pytest](https://pytest.org/).
Tests only exercise the public interface of each module and are laid out to
mirror the package (`src/pipeline_wizard/dag.py` is tested by
`tests/unit/test_dag.py`).

## Running

`pytest` is not a dependency of the package, so it needs installing in the same
environment as `pipeline_wizard` (for example, the conda environment from the
main README):

```bash
conda activate FGx_pipeline_wizard
pip install pytest
pip install -e .   # from the repository root, so tests import the package

pytest tests
```
