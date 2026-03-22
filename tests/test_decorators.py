"""
装饰器测试模块

测试日志装饰器、重试装饰器、计时装饰器等功能。
"""

import time
import pytest
from pathlib import Path

from gs2026.utils.decorators import (
    log_decorator,
    retry,
    timing,
    deprecated,
    singleton
)


class TestLogDecorator:
    """测试日志装饰器"""

    def test_log_decorator_basic(self, caplog):
        """测试基本日志功能"""
        @log_decorator(log_level="DEBUG")
        def add(a, b):
            return a + b

        result = add(1, 2)
        assert result == 3

    def test_log_decorator_with_args(self, caplog):
        """测试记录参数"""
        @log_decorator(log_level="INFO", log_args=True, log_result=True)
        def multiply(x, y):
            return x * y

        result = multiply(3, 4)
        assert result == 12

    def test_log_decorator_exception(self, caplog):
        """测试异常记录"""
        @log_decorator(log_exception=True)
        def raise_error():
            raise ValueError("测试错误")

        with pytest.raises(ValueError, match="测试错误"):
            raise_error()

    def test_log_decorator_no_args(self):
        """测试不记录参数"""
        @log_decorator(log_args=False)
        def process():
            return "done"

        result = process()
        assert result == "done"


class TestRetryDecorator:
    """测试重试装饰器"""

    def test_retry_success_first_attempt(self):
        """测试第一次就成功"""
        call_count = 0

        @retry(max_attempts=3, delay=0.1)
        def success_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = success_func()
        assert result == "success"
        assert call_count == 1

    def test_retry_success_after_failures(self):
        """测试失败后重试成功"""
        call_count = 0

        @retry(max_attempts=3, delay=0.1)
        def fail_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("连接失败")
            return "success"

        result = fail_then_success()
        assert result == "success"
        assert call_count == 3

    def test_retry_all_attempts_fail(self):
        """测试所有重试都失败"""
        call_count = 0

        @retry(max_attempts=3, delay=0.1)
        def always_fail():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("始终失败")

        with pytest.raises(ConnectionError):
            always_fail()

        assert call_count == 3

    def test_retry_specific_exception(self):
        """测试只捕获特定异常"""
        call_count = 0

        @retry(max_attempts=3, delay=0.1, exceptions=(ValueError,))
        def raise_different_errors():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("可重试错误")
            raise TypeError("不可重试错误")

        with pytest.raises(TypeError):
            raise_different_errors()

        assert call_count == 2


class TestTimingDecorator:
    """测试计时装饰器"""

    def test_timing_basic(self, caplog):
        """测试基本计时功能"""
        @timing
        def slow_function():
            time.sleep(0.1)
            return "done"

        result = slow_function()
        assert result == "done"

    def test_timing_with_args(self):
        """测试带参数的计时"""
        @timing
        def compute(x, y):
            time.sleep(0.05)
            return x + y

        result = compute(10, 20)
        assert result == 30


class TestDeprecatedDecorator:
    """测试弃用装饰器"""

    def test_deprecated_warning(self, caplog):
        """测试弃用警告"""
        @deprecated("请使用 new_func")
        def old_func():
            return "old"

        result = old_func()
        assert result == "old"

    def test_deprecated_no_reason(self):
        """测试无原因的弃用"""
        @deprecated()
        def func():
            return "value"

        result = func()
        assert result == "value"


class TestSingletonDecorator:
    """测试单例装饰器"""

    def test_singleton_same_instance(self):
        """测试返回相同实例"""
        @singleton
        class Database:
            def __init__(self):
                self.value = 0

        db1 = Database()
        db2 = Database()

        assert db1 is db2

    def test_singleton_shared_state(self):
        """测试共享状态"""
        @singleton
        class Config:
            def __init__(self):
                self.settings = {}

        config1 = Config()
        config1.settings["key"] = "value"

        config2 = Config()
        assert config2.settings["key"] == "value"


class TestIntegration:
    """集成测试"""

    def test_multiple_decorators(self):
        """测试多个装饰器组合"""
        @timing
        @retry(max_attempts=2, delay=0.1)
        @log_decorator(log_level="DEBUG")
        def complex_operation():
            return "success"

        result = complex_operation()
        assert result == "success"

    def test_decorator_preserves_metadata(self):
        """测试装饰器保留元数据"""
        @log_decorator()
        @retry(max_attempts=3)
        @timing
        def my_function():
            """我的函数文档"""
            return 42

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "我的函数文档"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
