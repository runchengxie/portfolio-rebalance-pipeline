.PHONY: test test-all test-int test-e2e coverage

test: ## 单元测试
	pytest

test-all: ## 全量测试
	pytest -m "unit or integration or e2e"

test-int: ## 集成测试
	pytest -m "integration" -q

test-e2e: ## 端到端
	pytest -m "e2e" -q

coverage: ## 覆盖率报告
	pytest --cov=stock_analysis --cov-report=term-missing
