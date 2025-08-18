# 测试结构说明

本项目的测试按照职责和复杂度分为三个层次：

## 单元测试 (Unit Tests)
位置：`tests/unit/`
标记：`@pytest.mark.unit`
运行：`pytest -m unit`

### 包含的测试文件：

- **`test_longport_symbols.py`** - 测试 `_to_lb_symbol` 函数的符号转换逻辑
  - 参数化测试各种股票代码格式
  - 测试边界情况和异常输入

- **`test_longport_client_unit.py`** - 测试 `LongPortClient` 类的方法（使用mock）
  - `quote_last` 方法的数据映射
  - `candles` 方法的参数传递
  - `submit_limit` 方法的订单构造
  - 价格和数量的 Decimal 精度处理

- **`test_cli_lb_commands.py`** - 测试CLI命令解析和分发逻辑
  - 命令路由测试
  - 参数解析测试
  - 错误处理测试

- **`test_longport_static.py`** - 静态检查测试
  - 依赖配置检查（pyproject.toml）
  - 文件结构验证
  - 导入语句检查

## 集成测试 (Integration Tests)
位置：`tests/integration/`
标记：`@pytest.mark.integration`
运行：`pytest -m integration`

### 包含的测试文件：

- **`test_longport_quote_integration.py`** - 真实API集成测试
  - 需要配置LongPort API凭据
  - 测试真实的股票报价获取
  - 测试历史K线数据获取
  - 包含网络错误和API限制的处理

## 端到端测试 (E2E Tests)
位置：`tests/e2e/`
标记：`@pytest.mark.e2e`
运行：`pytest -m e2e`

### 包含的测试文件：

- **`test_cli_lb_e2e.py`** - CLI端到端测试
  - 使用 subprocess 运行完整的CLI命令
  - 测试帮助信息显示
  - 测试错误处理和退出码
  - 测试真实API调用（需要凭据）

## 运行测试

### 运行所有测试
```bash
pytest
```

### 按类型运行测试
```bash
# 只运行单元测试（快速，不需要网络）
pytest -m unit

# 只运行集成测试（需要API凭据）
pytest -m integration

# 只运行端到端测试
pytest -m e2e
```

### 运行特定测试文件
```bash
# 运行符号转换测试
pytest tests/unit/test_longport_symbols.py -v

# 运行CLI测试
pytest tests/unit/test_cli_lb_commands.py -v
```

## 测试配置

### API凭据配置
集成测试和部分E2E测试需要LongPort API凭据：

```bash
# 在 .env 文件中配置
LONGPORT_APP_KEY=your_app_key
LONGPORT_APP_SECRET=your_app_secret
LONGPORT_ACCESS_TOKEN=your_access_token
```

### pytest标记
项目在 `pyproject.toml` 中预配置了测试标记：

```toml
[tool.pytest.ini_options]
markers = [
    "unit: 单元测试",
    "integration: 集成测试", 
    "e2e: 端到端测试"
]
```

## 测试原则

1. **单元测试**：快速、独立、不依赖外部服务
2. **集成测试**：测试与外部服务的真实交互
3. **端到端测试**：测试完整的用户工作流
4. **使用断言而非打印**：所有测试都使用断言验证结果
5. **适当的错误处理**：测试各种异常情况和边界条件

## 覆盖率

运行测试时会自动生成覆盖率报告。当前LongPort相关代码的覆盖率：
- `longport_client.py`: 83% 覆盖率
- `cli.py`: 27% 覆盖率（主要是LongPort相关部分）