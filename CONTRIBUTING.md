# Contributing to Test Shield

Thanks for helping make regression testing safer for Python developers.

## Quick Start

```bash
git clone https://github.com/dominicharmon-commits/test-shield.git
cd test-shield
pip install pytest
pytest tests/ -v
```

## What to Work On

Check the [Issues](https://github.com/dominicharmon-commits/test-shield/issues) tab. Good first issues are tagged `good first issue`.

## Pull Request Rules

1. **One fix per PR.** Don't bundle unrelated changes.
2. **Add tests.** If you fix a bug, add a test that proves it's fixed.
3. **Run the full suite.** `pytest tests/ -v` must pass.
4. **Keep analyze.py dependency-free.** No external packages — stdlib only.

## How analyze.py Works

```
git diff → parse_diff_files() → find_changed_functions() → build_call_graph() → output JSON
```

- `parse_diff_files()` — parses `git diff` output to find changed line ranges
- `find_changed_functions()` — maps changed lines to Python function definitions via AST
- `build_call_graph()` — walks every `.py` file looking for calls to changed functions
- `build_import_alias_map()` — tracks `from x import y as z` aliases
- `detect_dynamic_risks()` — flags getattr/importlib/decorator patterns

## Testing

```bash
pytest tests/ -v          # All tests
pytest tests/ -v -k E2E   # Just end-to-end
pytest tests/ -v --tb=long # Full traceback on failure
```

## Reporting Bugs

Include:
1. The Python code that wasn't traced correctly (minimal example)
2. Expected: which caller should have been found
3. Actual: what analyze.py reported
4. Python version and OS

## License

By contributing, you agree your code will be licensed under MIT.
