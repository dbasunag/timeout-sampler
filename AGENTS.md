# AGENTS.md — timeout-sampler

## Project Overview
Python utility library for timeout/retry polling patterns. Single module (~300 LOC), published on PyPI as `timeout-sampler`.

## Architecture
Single-file library: `timeout_sampler/__init__.py`
- `TimeoutSampler` — main class, generator-based polling with configurable exception filtering
- `TimeoutWatch` — elapsed time tracking utility
- `TimeoutExpiredError` — raised when timeout expires, carries `last_exp` and `elapsed_time`
- `retry` — decorator wrapping `TimeoutSampler` for function-level retry
- `ExceptionFilter`, `ExceptionsDict` — public type aliases for exception filter configuration

Tests: `tests/test_timeout_sampler.py` (single file, pytest)

## Setup & Commands
- Install: `uv sync`
- Test: `uv run pytest tests/`
- Lint: `uv run ruff check . && uv run ruff format --check .`
- Type check: `uv run mypy timeout_sampler/`
- All checks: run lint, type check, then tests — in that order

## Coding Standards
- Python >=3.10, `from __future__ import annotations` in all modules
- ruff: line-length=120, preview=true, fix=true
- mypy: strict (disallow_untyped_defs, disallow_incomplete_defs, check_untyped_defs)
- Type hints required on all public and private method signatures
- Docstrings: Google style with Args/Returns/Raises sections on all public methods
- Use `LOGGER` (from `python-simple-logger`) — never `print()`
- Broad exception catches must use `# noqa: BLE001` comment

## Testing
- Framework: pytest with IPython debugger (`--pdbcls=IPython.terminal.debugger:TerminalPdb`)
- Use `pytest.mark.parametrize` for related test cases — avoid boilerplate repetition
- Keep `wait_timeout` minimal in unit tests (1-2 seconds max) — tests must be fast
- Test both success and failure paths for new features

## Agent Guidelines

### Always
- Run tests after any code change
- Update docstrings when method signatures change
- Update README.md examples when public API changes
- Maintain backward compatibility — existing callers must not break
- Validate inputs at `__init__` time, not at runtime in hot paths

### Never
- Add dependencies to `pyproject.toml` without explicit approval
- Use `print()` — use `LOGGER` from `simple_logger`
- Edit files in `docs/` manually (see Generated Documentation below)
- Modify `__all__` without updating corresponding docstrings and README

### Ask First
- Before adding new public API surface (classes, functions, type aliases)
- Before changing exception hierarchy or error message formats
- Before bumping minimum Python version

## Generated Documentation
The `docs/` directory contains AI-generated documentation from docsfy.
**NEVER edit these files manually.** To update documentation, regenerate using docsfy.

## PR Guidelines
- Commit messages: conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`)
- Backward compatibility is required — breaking changes need explicit approval
- Update README examples when adding or changing public API
