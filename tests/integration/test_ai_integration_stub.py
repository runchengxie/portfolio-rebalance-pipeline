"""测试AI选股流程健壮性模块（纯模拟，不触网）

测试AI选股流程中的关键组件，包括：
- RateLimiter 滑动窗口节流
- Circuit 熔断开/合逻辑
- KeyPool 对401/403永久剔除 vs 429项目级冷却的分类
- 模拟client.models.generate_content超时、重试退避与成功后状态复位
- 解析结构化JSON的必填字段校验与异常分支
"""

import json
import threading
import time
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from stock_analysis.ai_stock_pick import (
    AIStockPick,
    Circuit,
    KeyPool,
    KeySlot,
    RateLimiter,
    call_with_pool,
    create_key_pool,
)


class TestRateLimiter:
    """测试滑动窗口限速器"""
    
    def test_initialization(self):
        """测试限速器初始化"""
        limiter = RateLimiter(max_calls=10, per_seconds=60)
        assert limiter.max_calls == 10
        assert limiter.per == 60
        assert len(limiter.calls) == 0
    
    def test_allow_within_limit(self):
        """测试在限制范围内的调用"""
        limiter = RateLimiter(max_calls=3, per_seconds=60)
        
        # 前3次调用应该被允许
        for _i in range(3):
            assert limiter.allow()
            limiter.record_call()
        
        # 第4次调用应该被拒绝
        assert not limiter.allow()
    
    def test_sliding_window_behavior(self):
        """测试滑动窗口行为"""
        limiter = RateLimiter(max_calls=2, per_seconds=1)  # 1秒内最多2次调用
        
        # 记录两次调用
        limiter.record_call()
        limiter.record_call()
        
        # 应该达到限制
        assert not limiter.allow()
        
        # 等待超过时间窗口
        time.sleep(1.1)
        
        # 现在应该可以再次调用
        assert limiter.allow()
    
    def test_wait_method(self):
        """测试等待方法"""
        limiter = RateLimiter(max_calls=1, per_seconds=1)
        
        # 第一次调用
        limiter.record_call()
        
        # 记录等待开始时间
        start_time = time.time()
        
        # 等待应该会阻塞直到可以再次调用
        limiter.wait()
        
        # 验证等待时间合理（应该接近1秒）
        elapsed = time.time() - start_time
        assert elapsed >= 0.9  # 允许一些时间误差
    
    def test_cleanup_old_calls(self):
        """测试清理过期调用记录"""
        limiter = RateLimiter(max_calls=5, per_seconds=1)
        
        # 添加一些调用记录
        for _ in range(3):
            limiter.record_call()
        
        assert len(limiter.calls) == 3
        
        # 等待超过时间窗口
        time.sleep(1.1)
        
        # 调用allow()应该清理过期记录
        limiter.allow()
        
        # 过期记录应该被清理
        assert len(limiter.calls) == 0


class TestCircuit:
    """测试熔断器"""
    
    def test_initialization(self):
        """测试熔断器初始化"""
        circuit = Circuit(fail_threshold=3, cooldown=30)
        assert circuit.fail_threshold == 3
        assert circuit.cooldown == 30
        assert circuit.failures == 0
        assert circuit.open_until == 0
    
    def test_allow_when_closed(self):
        """测试熔断器关闭时允许请求"""
        circuit = Circuit(fail_threshold=3, cooldown=30)
        assert circuit.allow()
    
    def test_record_failure_and_open(self):
        """测试记录失败并打开熔断器"""
        circuit = Circuit(fail_threshold=2, cooldown=1)
        
        # 第一次失败
        circuit.record_failure()
        assert circuit.failures == 1
        assert circuit.allow()  # 还未达到阈值
        
        # 第二次失败，应该打开熔断器
        circuit.record_failure()
        assert circuit.failures == 2
        assert not circuit.allow()  # 熔断器打开
    
    def test_cooldown_period(self):
        """测试冷却期行为"""
        circuit = Circuit(fail_threshold=1, cooldown=1)
        
        # 触发熔断
        circuit.record_failure()
        assert not circuit.allow()
        
        # 等待冷却期结束
        time.sleep(1.1)
        
        # 现在应该允许请求
        assert circuit.allow()
    
    def test_record_success_resets_failures(self):
        """测试记录成功重置失败计数"""
        circuit = Circuit(fail_threshold=3, cooldown=30)
        
        # 记录一些失败
        circuit.record_failure()
        circuit.record_failure()
        assert circuit.failures == 2
        
        # 记录成功应该重置失败计数
        circuit.record_success()
        assert circuit.failures == 0
    
    def test_multiple_failures_extend_cooldown(self):
        """测试多次失败延长冷却时间"""
        circuit = Circuit(fail_threshold=1, cooldown=1)
        
        # 第一次失败
        time.time()
        circuit.record_failure()
        first_open_until = circuit.open_until
        
        # 再次失败应该延长冷却时间
        circuit.record_failure()
        second_open_until = circuit.open_until
        
        assert second_open_until > first_open_until


class TestKeySlot:
    """测试API Key槽位"""
    
    def test_initialization(self):
        """测试槽位初始化"""
        mock_client = Mock()
        mock_limiter = Mock()
        
        slot = KeySlot("test_key", "api_key_123", mock_client, mock_limiter)
        
        assert slot.name == "test_key"
        assert slot.api_key == "api_key_123"
        assert slot.client == mock_client
        assert slot.limiter == mock_limiter
        assert isinstance(slot.circuit, Circuit)
        assert not slot.dead
        assert slot.next_ok_at == 0
    
    def test_slot_states(self):
        """测试槽位状态管理"""
        mock_client = Mock()
        mock_limiter = Mock()
        
        slot = KeySlot("test_key", "api_key_123", mock_client, mock_limiter)
        
        # 测试标记为死亡
        slot.dead = True
        assert slot.dead
        
        # 测试设置下次可用时间
        future_time = time.time() + 60
        slot.next_ok_at = future_time
        assert slot.next_ok_at == future_time


class TestKeyPool:
    """测试API Key池管理器"""
    
    def create_mock_slot(self, name: str, dead: bool = False, circuit_allow: bool = True, next_ok_at: float = 0) -> KeySlot:
        """创建模拟槽位"""
        mock_client = Mock()
        mock_limiter = Mock()
        
        slot = KeySlot(name, f"api_key_{name}", mock_client, mock_limiter)
        slot.dead = dead
        slot.next_ok_at = next_ok_at
        
        # 模拟熔断器行为
        slot.circuit.allow = Mock(return_value=circuit_allow)
        
        return slot
    
    def test_acquire_available_slot(self):
        """测试获取可用槽位"""
        slot1 = self.create_mock_slot("key1")
        slot2 = self.create_mock_slot("key2")
        
        pool = KeyPool([slot1, slot2])
        
        acquired_slot = pool.acquire()
        assert acquired_slot in [slot1, slot2]
    
    def test_skip_dead_slots(self):
        """测试跳过死亡槽位"""
        dead_slot = self.create_mock_slot("dead_key", dead=True)
        alive_slot = self.create_mock_slot("alive_key", dead=False)
        
        pool = KeyPool([dead_slot, alive_slot])
        
        acquired_slot = pool.acquire()
        assert acquired_slot == alive_slot
    
    def test_skip_circuit_open_slots(self):
        """测试跳过熔断器打开的槽位"""
        open_slot = self.create_mock_slot("open_key", circuit_allow=False)
        closed_slot = self.create_mock_slot("closed_key", circuit_allow=True)
        
        pool = KeyPool([open_slot, closed_slot])
        
        acquired_slot = pool.acquire()
        assert acquired_slot == closed_slot
    
    def test_skip_time_restricted_slots(self):
        """测试跳过时间限制的槽位"""
        future_time = time.time() + 60
        restricted_slot = self.create_mock_slot("restricted_key", next_ok_at=future_time)
        available_slot = self.create_mock_slot("available_key", next_ok_at=0)
        
        pool = KeyPool([restricted_slot, available_slot])
        
        acquired_slot = pool.acquire()
        assert acquired_slot == available_slot
    
    def test_project_cooldown(self):
        """测试项目级冷却"""
        slot = self.create_mock_slot("key1")
        pool = KeyPool([slot])
        
        # 设置项目级冷却
        pool.project_cooldown_until = time.time() + 60
        
        # 应该等待项目冷却结束
        with patch('time.sleep') as mock_sleep:
            # 模拟时间流逝
            with patch('time.time', side_effect=[time.time(), time.time() + 61]):
                acquired_slot = pool.acquire()
                assert acquired_slot == slot
                mock_sleep.assert_called()
    
    def test_report_success(self):
        """测试报告成功"""
        slot = self.create_mock_slot("key1")
        pool = KeyPool([slot])
        
        pool.report_success(slot)
        
        # 验证熔断器记录成功
        slot.circuit.record_success.assert_called_once()
        # 验证下次可用时间被重置
        assert slot.next_ok_at == time.time()
    
    def test_report_failure_401_403(self):
        """测试报告401/403错误（永久移除）"""
        slot = self.create_mock_slot("key1")
        pool = KeyPool([slot])
        
        # 模拟401错误
        error_401 = Exception("401 Unauthorized")
        pool.report_failure(slot, error_401)
        
        # 槽位应该被标记为死亡
        assert slot.dead
    
    def test_report_failure_429(self):
        """测试报告429错误（项目级冷却）"""
        slot = self.create_mock_slot("key1")
        pool = KeyPool([slot])
        
        # 模拟429错误
        error_429 = Exception("429 Too Many Requests")
        pool.report_failure(slot, error_429)
        
        # 应该设置项目级冷却
        assert pool.project_cooldown_until > time.time()
    
    def test_report_failure_other_errors(self):
        """测试报告其他错误（熔断器处理）"""
        slot = self.create_mock_slot("key1")
        pool = KeyPool([slot])
        
        # 模拟其他错误
        other_error = Exception("500 Internal Server Error")
        pool.report_failure(slot, other_error)
        
        # 应该记录到熔断器
        slot.circuit.record_failure.assert_called_once()
        # 应该设置软退避时间
        assert slot.next_ok_at > time.time()


class TestCallWithPool:
    """测试使用Key池的API调用函数"""
    
    def create_mock_pool(self, success_on_attempt: int = 1) -> Mock:
        """创建模拟Key池
        
        Args:
            success_on_attempt: 在第几次尝试时成功（1表示第一次就成功）
        """
        mock_pool = Mock()
        mock_slot = Mock()
        mock_slot.name = "test_key"
        
        # 模拟acquire方法
        mock_pool.acquire.return_value = mock_slot
        
        # 模拟成功和失败的报告方法
        mock_pool.report_success = Mock()
        mock_pool.report_failure = Mock()
        
        return mock_pool, mock_slot
    
    def test_successful_call_first_attempt(self):
        """测试第一次尝试就成功的调用"""
        mock_pool, mock_slot = self.create_mock_pool()
        
        # 创建成功的调用函数
        def successful_call(slot):
            return {"result": "success", "slot_name": slot.name}
        
        result = call_with_pool(mock_pool, successful_call, max_retries=3)
        
        # 验证结果
        assert result["result"] == "success"
        assert result["slot_name"] == "test_key"
        
        # 验证成功被报告
        mock_pool.report_success.assert_called_once_with(mock_slot)
        mock_pool.report_failure.assert_not_called()
    
    def test_retry_on_failure(self):
        """测试失败时的重试逻辑"""
        mock_pool, mock_slot = self.create_mock_pool()
        
        call_count = 0
        
        def failing_then_success_call(slot):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return {"result": "success after retries"}
        
        result = call_with_pool(mock_pool, failing_then_success_call, max_retries=5)
        
        # 验证最终成功
        assert result["result"] == "success after retries"
        
        # 验证重试次数
        assert call_count == 3
        
        # 验证失败和成功都被报告
        assert mock_pool.report_failure.call_count == 2  # 前两次失败
        mock_pool.report_success.assert_called_once()  # 最后一次成功
    
    def test_max_retries_exceeded(self):
        """测试超过最大重试次数"""
        mock_pool, mock_slot = self.create_mock_pool()
        
        def always_failing_call(slot):
            raise Exception("Always fails")
        
        with pytest.raises(Exception, match="Always fails"):
            call_with_pool(mock_pool, always_failing_call, max_retries=2)
        
        # 验证重试次数
        assert mock_pool.report_failure.call_count == 3  # 初始调用 + 2次重试
        mock_pool.report_success.assert_not_called()
    
    def test_exponential_backoff(self):
        """测试指数退避"""
        mock_pool, mock_slot = self.create_mock_pool()
        
        call_times = []
        
        def failing_call(slot):
            call_times.append(time.time())
            raise Exception("Retry with backoff")
        
        with patch('time.sleep') as mock_sleep:
            try:
                call_with_pool(mock_pool, failing_call, max_retries=2)
            except Exception:
                pass  # 预期会失败
        
        # 验证sleep被调用了正确的次数（重试之间）
        assert mock_sleep.call_count == 2
        
        # 验证退避时间递增
        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_calls[0] < sleep_calls[1]  # 第二次退避时间更长


class TestAIStockPick:
    """测试AI选股数据模型"""
    
    def test_valid_model_creation(self):
        """测试有效模型创建"""
        valid_data = {
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "confidence_score": 8,
            "reasoning": "Strong fundamentals and growth prospects"
        }
        
        pick = AIStockPick(**valid_data)
        
        assert pick.ticker == "AAPL"
        assert pick.company_name == "Apple Inc."
        assert pick.confidence_score == 8
        assert pick.reasoning == "Strong fundamentals and growth prospects"
    
    def test_confidence_score_validation(self):
        """测试置信度评分验证"""
        base_data = {
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "reasoning": "Test reasoning"
        }
        
        # 测试有效范围
        for score in [1, 5, 10]:
            data = {**base_data, "confidence_score": score}
            pick = AIStockPick(**data)
            assert pick.confidence_score == score
        
        # 测试无效范围
        for invalid_score in [0, 11, -1]:
            data = {**base_data, "confidence_score": invalid_score}
            with pytest.raises(ValidationError):
                AIStockPick(**data)
    
    def test_required_fields(self):
        """测试必填字段验证"""
        # 测试缺少ticker
        with pytest.raises(ValidationError):
            AIStockPick(
                company_name="Apple Inc.",
                confidence_score=8,
                reasoning="Test"
            )
        
        # 测试缺少company_name
        with pytest.raises(ValidationError):
            AIStockPick(
                ticker="AAPL",
                confidence_score=8,
                reasoning="Test"
            )
        
        # 测试缺少confidence_score
        with pytest.raises(ValidationError):
            AIStockPick(
                ticker="AAPL",
                company_name="Apple Inc.",
                reasoning="Test"
            )
        
        # 测试缺少reasoning
        with pytest.raises(ValidationError):
            AIStockPick(
                ticker="AAPL",
                company_name="Apple Inc.",
                confidence_score=8
            )
    
    def test_json_parsing(self):
        """测试JSON解析"""
        json_data = '''
        {
            "ticker": "MSFT",
            "company_name": "Microsoft Corporation",
            "confidence_score": 9,
            "reasoning": "Excellent cloud business growth and strong financials"
        }
        '''
        
        data = json.loads(json_data)
        pick = AIStockPick(**data)
        
        assert pick.ticker == "MSFT"
        assert pick.company_name == "Microsoft Corporation"
        assert pick.confidence_score == 9
    
    def test_invalid_json_structure(self):
        """测试无效JSON结构处理"""
        # 测试额外字段（应该被忽略）
        data_with_extra = {
            "ticker": "GOOGL",
            "company_name": "Alphabet Inc.",
            "confidence_score": 7,
            "reasoning": "Strong search and cloud business",
            "extra_field": "should be ignored"
        }
        
        pick = AIStockPick(**data_with_extra)
        assert pick.ticker == "GOOGL"
        assert not hasattr(pick, 'extra_field')


class TestCreateKeyPool:
    """测试Key池创建函数"""
    
    @patch.dict('os.environ', {
        'GEMINI_API_KEY': 'key1',
        'GEMINI_API_KEY_2': 'key2',
        'GEMINI_API_KEY_3': 'key3'
    })
    @patch('stock_analysis.ai_stock_pick.genai.GenerativeModel')
    def test_create_pool_with_all_keys(self, mock_model):
        """测试使用所有三个API key创建池"""
        # 模拟GenerativeModel
        mock_model.return_value = Mock()
        
        pool = create_key_pool()
        
        assert isinstance(pool, KeyPool)
        assert len(pool.slots) == 3
        
        # 验证槽位名称
        slot_names = [slot.name for slot in pool.slots]
        assert "GEMINI_API_KEY" in slot_names
        assert "GEMINI_API_KEY_2" in slot_names
        assert "GEMINI_API_KEY_3" in slot_names
    
    @patch.dict('os.environ', {
        'GEMINI_API_KEY': 'key1',
        'GEMINI_API_KEY_2': 'key2'
        # 缺少GEMINI_API_KEY_3
    })
    @patch('stock_analysis.ai_stock_pick.genai.GenerativeModel')
    def test_create_pool_with_partial_keys(self, mock_model):
        """测试使用部分API key创建池"""
        mock_model.return_value = Mock()
        
        pool = create_key_pool()
        
        assert isinstance(pool, KeyPool)
        assert len(pool.slots) == 2
    
    @patch.dict('os.environ', {}, clear=True)
    def test_create_pool_no_keys(self):
        """测试没有API key时的异常处理"""
        with pytest.raises(ValueError, match="没有可用的 GEMINI_API_KEY"):
            create_key_pool()
    
    @patch.dict('os.environ', {
        'GEMINI_API_KEY': '',  # 空字符串应该被过滤
        'GEMINI_API_KEY_2': 'key2'
    })
    @patch('stock_analysis.ai_stock_pick.genai.GenerativeModel')
    def test_create_pool_filter_empty_keys(self, mock_model):
        """测试过滤空API key"""
        mock_model.return_value = Mock()
        
        pool = create_key_pool()
        
        assert len(pool.slots) == 1
        assert pool.slots[0].name == "GEMINI_API_KEY_2"


class TestAIIntegrationScenarios:
    """AI集成场景测试"""
    
    def test_complete_ai_workflow_simulation(self):
        """完整AI工作流程模拟测试"""
        # 1. 创建模拟Key池
        mock_slot1 = Mock()
        mock_slot1.name = "key1"
        mock_slot1.dead = False
        mock_slot1.next_ok_at = 0
        mock_slot1.circuit.allow.return_value = True
        mock_slot1.limiter.allow.return_value = True
        
        mock_pool = Mock()
        mock_pool.acquire.return_value = mock_slot1
        mock_pool.report_success = Mock()
        mock_pool.report_failure = Mock()
        
        # 2. 模拟AI API调用
        def mock_ai_call(slot):
            # 模拟成功的AI响应
            return {
                "ticker": "AAPL",
                "company_name": "Apple Inc.",
                "confidence_score": 8,
                "reasoning": "Strong fundamentals and market position"
            }
        
        # 3. 执行调用
        result = call_with_pool(mock_pool, mock_ai_call, max_retries=3)
        
        # 4. 验证结果
        assert result["ticker"] == "AAPL"
        assert result["confidence_score"] == 8
        
        # 5. 验证成功被报告
        mock_pool.report_success.assert_called_once_with(mock_slot1)
    
    def test_resilience_under_multiple_failures(self):
        """测试多重失败下的韧性"""
        # 创建多个槽位，模拟不同的失败场景
        dead_slot = Mock()
        dead_slot.name = "dead_key"
        dead_slot.dead = True
        
        circuit_open_slot = Mock()
        circuit_open_slot.name = "circuit_open_key"
        circuit_open_slot.dead = False
        circuit_open_slot.next_ok_at = 0
        circuit_open_slot.circuit.allow.return_value = False
        
        working_slot = Mock()
        working_slot.name = "working_key"
        working_slot.dead = False
        working_slot.next_ok_at = 0
        working_slot.circuit.allow.return_value = True
        
        # 模拟池的acquire逻辑
        def mock_acquire():
            # 跳过死亡和熔断的槽位，返回工作的槽位
            candidates = [s for s in [dead_slot, circuit_open_slot, working_slot]
                         if not s.dead and s.circuit.allow() and time.time() >= s.next_ok_at]
            return candidates[0] if candidates else None
        
        mock_pool = Mock()
        mock_pool.acquire = mock_acquire
        mock_pool.report_success = Mock()
        
        def successful_call(slot):
            return {"result": "success", "slot": slot.name}
        
        result = call_with_pool(mock_pool, successful_call, max_retries=3)
        
        # 应该使用工作的槽位
        assert result["slot"] == "working_key"
    
    def test_json_parsing_error_handling(self):
        """测试JSON解析错误处理"""
        # 测试无效JSON
        invalid_json_cases = [
            '{"ticker": "AAPL", "confidence_score": "not_a_number"}',  # 类型错误
            '{"ticker": "AAPL"}',  # 缺少必填字段
            '{"ticker": "AAPL", "confidence_score": 15}',  # 超出范围
            'invalid json string',  # 无效JSON格式
        ]
        
        for invalid_json in invalid_json_cases:
            try:
                data = json.loads(invalid_json)
                AIStockPick(**data)
                raise AssertionError(f"Should have raised exception for: {invalid_json}")
            except (json.JSONDecodeError, ValidationError, TypeError):
                # 预期的异常
                pass
    
    def test_concurrent_key_pool_access(self):
        """测试并发访问Key池"""
        # 创建真实的Key池进行并发测试
        mock_client = Mock()
        mock_limiter = Mock()
        mock_limiter.allow.return_value = True
        
        slots = []
        for i in range(3):
            slot = KeySlot(f"key_{i}", f"api_key_{i}", mock_client, mock_limiter)
            slots.append(slot)
        
        pool = KeyPool(slots)
        
        # 并发获取槽位
        acquired_slots = []
        
        def acquire_slot():
            slot = pool.acquire()
            acquired_slots.append(slot)
            time.sleep(0.1)  # 模拟使用时间
        
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=acquire_slot)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # 验证所有线程都获得了槽位
        assert len(acquired_slots) == 3
        # 验证没有重复分配
        assert len(set(acquired_slots)) == 3