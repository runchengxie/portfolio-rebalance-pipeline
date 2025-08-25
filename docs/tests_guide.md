# 测试指南

本项目使用pytest进行测试，测试分为多个类别以确保CI/CD的效率和稳定性。

## 测试分类

### 单元测试 (Unit Tests)
- **标记**: `@pytest.mark.unit`
- **特点**: 快速、独立、不依赖外部资源
- **包含**: 函数逻辑测试、数据处理测试、算法验证等
- **运行时间**: 通常 < 1秒

### 集成测试 (Integration Tests)
- **标记**: `@pytest.mark.integration`
- **特点**: 较慢、可能依赖外部API或数据库
- **包含**: API调用测试、数据库操作测试、文件I/O测试
- **运行时间**: 可能需要几秒到几分钟
- **注意**: 默认情况下被跳过，需要显式运行

### 端到端测试 (E2E Tests)
- **标记**: `@pytest.mark.e2e`
- **特点**: 测试完整的工作流程
- **包含**: CLI命令测试、完整流程测试
- **运行时间**: 可能需要较长时间

### 其他标记
- **`@pytest.mark.slow`**: 运行时间较长的测试
- **`@pytest.mark.requires_api`**: 需要外部API访问的测试
- **`@pytest.mark.requires_db`**: 需要数据库访问的测试

## 运行测试

### 默认运行（仅单元测试）
```bash
# 运行所有单元测试，跳过integration测试
pytest

# 或者显式指定
pytest -m "not integration"
```

### 运行所有测试
```bash
# 运行包括integration测试在内的所有测试
pytest -m ""

# 或者
pytest --no-cov -m ""
```

### 运行特定类型的测试
```bash
# 仅运行单元测试
pytest -m "unit"

# 仅运行集成测试
pytest -m "integration"

# 仅运行端到端测试
pytest -m "e2e"

# 运行快速测试（排除慢测试）
pytest -m "not slow"

# 运行不需要API的测试
pytest -m "not requires_api"
```

### 运行特定目录的测试
```bash
# 仅运行单元测试目录
pytest tests/unit/

# 仅运行集成测试目录
pytest tests/integration/

# 仅运行端到端测试目录
pytest tests/e2e/
```

### 覆盖率报告
```bash
# 生成详细的覆盖率报告
pytest --cov=stock_analysis --cov-report=html

# 查看未覆盖的行
pytest --cov=stock_analysis --cov-report=term-missing

# 设置覆盖率阈值
pytest --cov=stock_analysis --cov-fail-under=80
```

## CI/CD 配置

### 默认行为
- CI默认只运行单元测试（快速反馈）
- 覆盖率要求达到75%
- 集成测试被跳过以避免外部依赖问题

### 完整测试
在需要完整测试时（如发布前），可以运行：
```bash
pytest -m "" --cov=stock_analysis --cov-report=term-missing
```

## 测试编写指南

### 标记测试
```python
import pytest

@pytest.mark.unit
def test_fast_function():
    """快速的单元测试"""
    assert True

@pytest.mark.integration
@pytest.mark.requires_api
def test_api_call():
    """需要API访问的集成测试"""
    # 测试代码
    pass

@pytest.mark.integration
@pytest.mark.requires_db
def test_database_operation():
    """需要数据库的集成测试"""
    # 测试代码
    pass

@pytest.mark.slow
def test_long_running_process():
    """运行时间较长的测试"""
    # 测试代码
    pass
```

### 跳过条件
```python
@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("API_KEY"),
    reason="API密钥未配置，跳过集成测试"
)
def test_with_api_key():
    """需要API密钥的测试"""
    pass
```

### 参数化测试
```python
@pytest.mark.unit
@pytest.mark.parametrize("input,expected", [
    ("test", "TEST"),
    ("hello", "HELLO"),
])
def test_uppercase(input, expected):
    assert input.upper() == expected
```

## 故障排除

### 常见问题

1. **集成测试失败**
   - 检查API密钥是否配置
   - 检查网络连接
   - 检查外部服务状态

2. **覆盖率不足**
   - 运行 `pytest --cov=stock_analysis --cov-report=html` 查看详细报告
   - 添加缺失的测试用例

3. **测试运行缓慢**
   - 使用 `pytest -m "not slow"` 跳过慢测试
   - 检查是否有未标记的慢测试

### 调试测试
```bash
# 显示详细输出
pytest -v

# 显示print语句
pytest -s

# 在第一个失败时停止
pytest -x

# 显示最慢的10个测试
pytest --durations=10
```

## 最佳实践

1. **测试隔离**: 每个测试应该独立，不依赖其他测试的状态
2. **快速反馈**: 单元测试应该快速运行，提供即时反馈
3. **合理标记**: 正确标记测试类型，确保CI效率
4. **模拟外部依赖**: 在单元测试中使用mock避免外部依赖
5. **清晰命名**: 测试名称应该清楚描述测试的内容和预期
6. **适当覆盖**: 关注关键路径和边界情况的测试覆盖

## 示例测试结构

```
tests/
├── unit/                    # 单元测试
│   ├── test_tidy_ticker.py
│   ├── test_preliminary_selection.py
│   └── test_ai_result_parsing.py
├── integration/             # 集成测试
│   ├── test_db_io.py
│   ├── test_longbridge_quote_integration.py
│   └── test_price_data_completeness.py
├── e2e/                     # 端到端测试
│   ├── test_cli_smoke.py
│   └── test_cli_lb_e2e.py
└── README.md               # 本文件
```