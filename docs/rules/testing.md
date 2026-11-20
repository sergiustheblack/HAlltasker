# Tests and checks

- Tests: `pytest`, names `test_<what we check>_<expectation>`. One assert
  block per behavior.
- Fakes from `tests/core/fakes.py`, not `MagicMock`, for plugins and the
  store.

## Running the checks

Activate the virtualenv first:

```
source ./.venv/bin/activate
ruff check . && ruff format --check . && pytest -q
```

All three commands must finish without errors. If `ruff format --check`
complains, run `ruff format .` and repeat.

## Confirming Home Assistant signatures

The HA version is pinned in `requirements_dev.txt`. Inspect the installed
package rather than searching the internet:

```
python -c "import homeassistant.components.todo.const as c; print([f.name for f in c.TodoListEntityFeature])"
```
