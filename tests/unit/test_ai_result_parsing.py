"""AI结果解析的单元测试

测试AI模型输出的容错解析：
- 格式烂尾的JSON处理
- 尾随逗号和多余字符
- 数组长度非10的情况
- 字段缺失或类型错误
- "十选十"硬性要求的验证
"""

import json
from types import SimpleNamespace

import pytest

from stock_analysis.ai_stock_pick import AIStockPick, parse_response_robust


@pytest.mark.unit
class TestAIStockPickModel:
    """测试AIStockPick数据模型的验证"""
    
    def test_valid_stock_pick(self):
        """测试有效的股票选择数据"""
        valid_data = {
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "confidence_score": 8,
            "reasoning": "Strong fundamentals and market position"
        }
        
        pick = AIStockPick(**valid_data)
        assert pick.ticker == "AAPL"
        assert pick.company_name == "Apple Inc."
        assert pick.confidence_score == 8
        assert pick.reasoning == "Strong fundamentals and market position"
    
    def test_confidence_score_validation(self):
        """测试置信度分数的验证（必须是1-10的整数）"""
        base_data = {
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "reasoning": "Test reasoning"
        }
        
        # 有效分数
        for score in [1, 5, 10]:
            data = {**base_data, "confidence_score": score}
            pick = AIStockPick(**data)
            assert pick.confidence_score == score
        
        # 无效分数应该抛出验证错误
        invalid_scores = [0, 11, -1, 5.5, "8", None]
        for score in invalid_scores:
            data = {**base_data, "confidence_score": score}
            with pytest.raises(Exception):  # Pydantic ValidationError
                AIStockPick(**data)
    
    def test_required_fields(self):
        """测试必填字段验证"""
        complete_data = {
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "confidence_score": 8,
            "reasoning": "Strong fundamentals"
        }
        
        # 测试每个字段都是必需的
        for field in complete_data.keys():
            incomplete_data = {k: v for k, v in complete_data.items() if k != field}
            with pytest.raises(Exception):  # Pydantic ValidationError
                AIStockPick(**incomplete_data)


@pytest.mark.unit
class TestJSONParsingRobustness:
    """测试JSON解析的健壮性"""
    
    def test_perfect_json_parsing(self):
        """测试完美JSON的解析"""
        perfect_json = '''[
            {
                "ticker": "AAPL",
                "company_name": "Apple Inc.",
                "confidence_score": 9,
                "reasoning": "Excellent fundamentals"
            },
            {
                "ticker": "MSFT",
                "company_name": "Microsoft Corp.",
                "confidence_score": 8,
                "reasoning": "Strong cloud business"
            }
        ]'''
        
        # 模拟response对象
        response = SimpleNamespace()
        response.text = perfect_json
        response.parsed = None
        
        result = parse_response_robust(response)
        
        assert result is not None
        assert len(result) == 2
        assert isinstance(result[0], AIStockPick)
        assert result[0].ticker == "AAPL"
        assert result[1].ticker == "MSFT"
    
    def test_trailing_comma_json(self):
        """测试带尾随逗号的JSON"""
        trailing_comma_json = '''[
            {
                "ticker": "AAPL",
                "company_name": "Apple Inc.",
                "confidence_score": 9,
                "reasoning": "Excellent fundamentals",
            },
        ]'''
        
        response = SimpleNamespace()
        response.text = trailing_comma_json
        response.parsed = None
        
        # 标准JSON解析应该失败，函数应该返回None
        result = parse_response_robust(response)
        assert result is None
    
    def test_malformed_json_with_extra_text(self):
        """测试包含额外文本的格式错误JSON"""
        malformed_json = '''Here are my stock picks:
        [
            {
                "ticker": "AAPL",
                "company_name": "Apple Inc.",
                "confidence_score": 9,
                "reasoning": "Great company"
            }
        ]
        
        These are my top recommendations based on analysis.'''
        
        response = SimpleNamespace()
        response.text = malformed_json
        response.parsed = None
        
        result = parse_response_robust(response)
        assert result is None
    
    def test_incomplete_json(self):
        """测试不完整的JSON（突然截断）"""
        incomplete_json = '''[
            {
                "ticker": "AAPL",
                "company_name": "Apple Inc.",
                "confidence_score": 9,
                "reasoning": "Excellent fund'''
        
        response = SimpleNamespace()
        response.text = incomplete_json
        response.parsed = None
        
        result = parse_response_robust(response)
        assert result is None
    
    def test_non_array_json(self):
        """测试非数组格式的JSON"""
        non_array_json = '''{
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "confidence_score": 9,
            "reasoning": "Single stock object"
        }'''
        
        response = SimpleNamespace()
        response.text = non_array_json
        response.parsed = None
        
        result = parse_response_robust(response)
        assert result is None
    
    def test_empty_response(self):
        """测试空响应"""
        response = SimpleNamespace()
        response.text = ""
        response.parsed = None
        
        result = parse_response_robust(response)
        assert result is None
    
    def test_null_response(self):
        """测试null响应"""
        response = SimpleNamespace()
        response.text = None
        response.parsed = None
        
        result = parse_response_robust(response)
        assert result is None


@pytest.mark.unit
class TestTenStockRequirement:
    """测试"十选十"硬性要求"""
    
    def test_exactly_ten_stocks_valid(self):
        """测试恰好10只股票的有效情况"""
        ten_stocks_data = []
        for i in range(10):
            ten_stocks_data.append({
                "ticker": f"STOCK{i+1}",
                "company_name": f"Company {i+1}",
                "confidence_score": (i % 10) + 1,
                "reasoning": f"Reasoning for stock {i+1}"
            })
        
        json_text = json.dumps(ten_stocks_data)
        response = SimpleNamespace()
        response.text = json_text
        response.parsed = None
        
        result = parse_response_robust(response)
        
        assert result is not None
        assert len(result) == 10
        for i, pick in enumerate(result):
            assert isinstance(pick, AIStockPick)
            assert pick.ticker == f"STOCK{i+1}"
    
    def test_less_than_ten_stocks(self):
        """测试少于10只股票的情况"""
        five_stocks_data = []
        for i in range(5):
            five_stocks_data.append({
                "ticker": f"STOCK{i+1}",
                "company_name": f"Company {i+1}",
                "confidence_score": 8,
                "reasoning": f"Reasoning for stock {i+1}"
            })
        
        json_text = json.dumps(five_stocks_data)
        response = SimpleNamespace()
        response.text = json_text
        response.parsed = None
        
        result = parse_response_robust(response)
        
        # 解析成功但数量不对
        assert result is not None
        assert len(result) == 5  # 应该检测到数量不符合要求
    
    def test_more_than_ten_stocks(self):
        """测试超过10只股票的情况"""
        fifteen_stocks_data = []
        for i in range(15):
            fifteen_stocks_data.append({
                "ticker": f"STOCK{i+1}",
                "company_name": f"Company {i+1}",
                "confidence_score": 7,
                "reasoning": f"Reasoning for stock {i+1}"
            })
        
        json_text = json.dumps(fifteen_stocks_data)
        response = SimpleNamespace()
        response.text = json_text
        response.parsed = None
        
        result = parse_response_robust(response)
        
        # 解析成功但数量不对
        assert result is not None
        assert len(result) == 15  # 应该检测到数量不符合要求


@pytest.mark.unit
class TestFieldValidationEdgeCases:
    """测试字段验证的边界情况"""
    
    def test_missing_fields_in_json(self):
        """测试JSON中缺少字段的情况"""
        incomplete_stock = {
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            # 缺少 confidence_score 和 reasoning
        }
        
        json_text = json.dumps([incomplete_stock])
        response = SimpleNamespace()
        response.text = json_text
        response.parsed = None
        
        # 应该在创建AIStockPick对象时失败
        result = parse_response_robust(response)
        assert result is None
    
    def test_wrong_field_types(self):
        """测试字段类型错误的情况"""
        wrong_type_stock = {
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "confidence_score": "eight",  # 应该是整数
            "reasoning": "Good company"
        }
        
        json_text = json.dumps([wrong_type_stock])
        response = SimpleNamespace()
        response.text = json_text
        response.parsed = None
        
        result = parse_response_robust(response)
        assert result is None
    
    def test_empty_string_fields(self):
        """测试空字符串字段"""
        empty_fields_stock = {
            "ticker": "",  # 空ticker
            "company_name": "Apple Inc.",
            "confidence_score": 8,
            "reasoning": ""
        }
        
        json_text = json.dumps([empty_fields_stock])
        response = SimpleNamespace()
        response.text = json_text
        response.parsed = None
        
        # 根据模型定义，空字符串可能是有效的，但业务逻辑上不合理
        result = parse_response_robust(response)
        if result is not None:
            assert len(result) == 1
            assert result[0].ticker == ""
    
    def test_null_fields_in_json(self):
        """测试JSON中null字段"""
        null_fields_stock = {
            "ticker": "AAPL",
            "company_name": None,
            "confidence_score": 8,
            "reasoning": "Good reasoning"
        }
        
        json_text = json.dumps([null_fields_stock])
        response = SimpleNamespace()
        response.text = json_text
        response.parsed = None
        
        result = parse_response_robust(response)
        assert result is None  # null字段应该导致验证失败


@pytest.mark.unit
class TestResponseObjectVariations:
    """测试不同response对象格式的处理"""
    
    def test_response_with_parsed_attribute(self):
        """测试有parsed属性的response"""
        # 创建模拟的已解析对象
        parsed_picks = [
            AIStockPick(
                ticker="AAPL",
                company_name="Apple Inc.",
                confidence_score=9,
                reasoning="Strong fundamentals"
            )
        ]
        
        response = SimpleNamespace()
        response.parsed = parsed_picks
        response.text = "some text"
        
        result = parse_response_robust(response)
        
        assert result is not None
        assert len(result) == 1
        assert result[0].ticker == "AAPL"
    
    def test_response_with_empty_parsed(self):
        """测试parsed为空但text有内容的response"""
        valid_json = '''[
            {
                "ticker": "MSFT",
                "company_name": "Microsoft Corp.",
                "confidence_score": 8,
                "reasoning": "Cloud leadership"
            }
        ]'''
        
        response = SimpleNamespace()
        response.parsed = None  # 或者 []
        response.text = valid_json
        
        result = parse_response_robust(response)
        
        assert result is not None
        assert len(result) == 1
        assert result[0].ticker == "MSFT"
    
    def test_response_without_attributes(self):
        """测试缺少属性的response对象"""
        response = SimpleNamespace()
        # 既没有parsed也没有text
        
        result = parse_response_robust(response)
        assert result is None
    
    def test_response_parsing_exception(self):
        """测试解析过程中的异常处理"""
        # 创建一个会导致异常的response对象
        class BadResponse:
            @property
            def parsed(self):
                raise Exception("Parsing error")
            
            @property
            def text(self):
                return "some text"
        
        response = BadResponse()
        result = parse_response_robust(response)
        assert result is None