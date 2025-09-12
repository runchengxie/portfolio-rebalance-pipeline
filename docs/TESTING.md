# 测试约定

本项目使用 [pytest](https://docs.pytest.org/) 运行测试，以下内容说明我们在仓库中约定的规则。

## 标记规范

- `unit`: 快速、无外部依赖的单元测试。
- `integration`: 访问外部 API、数据库或执行 I/O 的测试。
- `e2e`: 通过 CLI 覆盖完整工作流的端到端测试。
- `requires_api`: 需要外部 API 凭证时使用，与 `integration`/`e2e` 组合。
- `requires_db`: 需要数据库时使用。
- `slow`: 长时间运行的测试，可与其他标记组合使用。

默认行为：`pytest` 只运行 `unit`，`integration`/`e2e`/`slow` 测试会被跳过。

## 覆盖率

`pytest.ini` 启用了 `--cov=stock_analysis --cov-report=term-missing --cov-fail-under=75`，提交前需保持总体覆盖率 ≥75%。

## 目录结构

```
tests/
├─ unit/
├─ integration/
└─ e2e/
```

每类测试必须放在对应目录，文件名 `test_*.py`，函数名 `test_*`。

## 环境变量

下列环境变量缺失时，对应测试会自动 `skip`：

| 场景 | 环境变量 |
| --- | --- |
| LongPort API | `LONGPORT_APP_KEY`, `LONGPORT_APP_SECRET`, `LONGPORT_ACCESS_TOKEN`, `LONGPORT_REGION`（默认 `hk`，内地账户设为 `cn`） |
| Gemini AI | `GEMINI_API_KEY`, `GEMINI_API_KEY_2`, `GEMINI_API_KEY_3` |

## 常用命令

- 快速检查（默认，仅单元测试）
  ```bash
  pytest
  ```
- 仅运行集成测试
  ```bash
  pytest -m "integration" -o addopts=
  ```
- 仅运行端到端测试
  ```bash
  pytest -m "e2e" -o addopts=
  ```
- 发布前运行全量测试
  ```bash
  pytest -m "" -o addopts=
  ```

上述命令中的 `-o addopts=` 会清除 `pytest.ini` 中的默认过滤条件。
