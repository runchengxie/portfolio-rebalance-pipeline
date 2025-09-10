# Repository Guidelines

## Project Structure & Module Organization
- Source: `src/stock_analysis/`
  - CLI: `cli.py`, subcommands in `commands/`
  - Strategies & engine: `backtest/` (engine, prep, strategies)
  - Data loading: `services/data/`
  - AI selection: `services/selection/`
  - Broker: `broker/` (LongPort client and stubs)
  - Utilities: `utils/`, `logging/`, `io/`, `renderers/`, `config/`
- Data & outputs: `data/` (CSVs, DB), `outputs/` (charts, JSON, logs)
- Tests: `tests/` with `unit/`, `integration/`, `e2e/`

## Build, Test, and Development Commands
- Install (dev): `uv sync --extra dev` or `pip install -e .`
- Lint/format: `ruff --fix .` then `ruff format .`
- Type-check: `mypy src`
- Tests (75%+ cov): `pytest --cov=stock_analysis`
  - Suites: `pytest -m unit`, `pytest -m integration -o addopts=`, `pytest -m e2e`
- Pre-commit: `pre-commit install && pre-commit run -a`
- CLI examples:
  - Load data: `stockq load-data` (see `--skip-prices`, `--only-prices`)
  - Backtests: `stockq backtest ai|quant|spy`
  - AI pick: `stockq ai-pick`
  - Whitelist: `stockq gen-whitelist --from preliminary`
  - LongPort: `stockq lb-account`, `stockq lb-rebalance targets.json`, `stockq lb-config`

## Coding Style & Naming Conventions
- Python 3.10; 4-space indent; 88-char lines; prefer double quotes.
- Use type hints throughout. Keep business logic in `services/`; keep CLI thin and composable.
- Naming: modules/functions `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE_CASE`.

## Testing Guidelines
- Framework: `pytest` with markers `unit`, `integration`, `e2e`.
- Naming: files `tests/test_*.py`, functions `def test_*`.
- Run fast logic in `unit/`; broader flows in `integration/` and end-to-end CLI in `e2e/`.

## Commit & Pull Request Guidelines
- Commits: short, imperative, scoped (e.g., `refactor: streamline CLI`, `fix: handle empty quotes`).
- PRs: include description, rationale, relevant CLI output (snippets/screenshots), linked issues, and commands run (`ruff`, `mypy`, `pytest`). Note any config/env changes.

## Security & Configuration Tips
- Seed `.env` from `.env.example`; never commit secrets or API keys.
- Copy `config/template.yaml` to `config/config.yaml` before running.
- Use dry runs first; real LongPort trading only with `--execute`.
- Keep large CSVs/SQLite in `data/`; avoid committing generated artifacts in `outputs/`.
