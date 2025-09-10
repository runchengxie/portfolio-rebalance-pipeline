# Repository Guidelines

## Project Structure & Module Organization
- Source: `src/stock_analysis/` — CLI (`cli.py`); strategies (`preliminary_selection.py`, `ai_stock_pick.py`); backtests (`backtest_*`); broker (`broker/`); plus `services/`, `renderers/`, and `utils/`.
- Config: copy `config/template.yaml` to `config/config.yaml` before running.
- Data: `data/` for CSVs and `financial_data.db`; outputs in `outputs/`.
- Tests: `tests/` with `unit/`, `integration/`, and `e2e/`; markers set in `pyproject.toml`.

## Build, Test, and Development Commands
- Install (dev): `uv sync --extra dev` or `pip install -e .`.
- Pre-commit: `pre-commit install && pre-commit run -a`.
- Lint/format: `ruff --fix .` then `ruff format .`.
- Type-check: `mypy src`.
- Test: `pytest --cov=stock_analysis` (≥ 75% coverage); suites: `pytest -m unit` or `pytest -m integration -o addopts=`.
- CLI: `stockq load-data`, `stockq preliminary`, `stockq ai-pick`, `stockq backtest ai`, `stockq lb-account --env test|real|both`.

## Coding Style & Naming Conventions
- Python 3.10; 4-space indent; 88-char lines; prefer double quotes.
- Use type hints everywhere. Keep business logic in `services/`; keep CLI glue thin and composable.
- Naming: modules/functions `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE_CASE`.

## Testing Guidelines
- Framework: `pytest` with `unit`, `integration`, `e2e` markers.
- Naming: files `tests/test_*.py`, functions `def test_*`.
- Scope: fast tests in `unit/`; broader flows in `integration/` and `e2e/`.

## Commit & Pull Request Guidelines
- Commits: short, imperative, scoped (e.g., `refactor: streamline CLI`, `fix: handle empty quotes`). Update `pyproject.toml`/`uv.lock` when deps change.
- PRs: include description, rationale, relevant CLI output (snippets/screenshots), linked issues, and commands run (lint, mypy, pytest). Note any config/env changes.

## Security & Configuration Tips
- Seed `.env` from `.env.example`; never commit secrets or API keys.
- Copy `config/template.yaml` to `config/config.yaml` before running.
- Use dry runs first; real LongPort trading only with `--execute` and correct `--env`.
- Keep large CSVs/SQLite in `data/`; avoid committing generated artifacts.

