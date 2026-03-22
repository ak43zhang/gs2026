"""
测试运行脚本

用于在没有 pytest 的情况下运行基本测试。
"""

import sys
import time
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gs2026.utils.decorators import (
    log_decorator,
    retry,
    timing,
    deprecated,
    singleton
)


class TestRunner:
    """测试运行器"""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []

    def test(self, name):
        """装饰器：标记测试方法"""
        def decorator(func):
            self.tests.append((name, func))
            return func
        return decorator

    def run(self):
        """运行所有测试"""
        print("=" * 60)
        print("运行装饰器测试")
        print("=" * 60)

        for name, func in self.tests:
            try:
                func()
                print(f"✅ {name}")
                self.passed += 1
            except Exception as e:
                print(f"❌ {name}: {e}")
                self.failed += 1

        print("=" * 60)
        print(f"结果: {self.passed} 通过, {self.failed} 失败")
        print("=" * 60)

        return self.failed == 0


# 创建测试运行器
runner = TestRunner()


# ============ 日志装饰器测试 ============

@runner.test("日志装饰器 - 基本功能")
def test_log_decorator_basic():
    @log_decorator(log_level="DEBUG", log_args=True)
    def add(a, b):
        return a + b

    result = add(1, 2)
    assert result == 3, f"期望 3, 得到 {result}"


@runner.test("日志装饰器 - 记录返回值")
def test_log_decorator_result():
    @log_decorator(log_level="DEBUG", log_args=True, log_result=True)
    def multiply(x, y):
        return x * y

    result = multiply(3, 4)
    assert result == 12, f"期望 12, 得到 {result}"


@runner.test("日志装饰器 - 异常记录")
def test_log_decorator_exception():
    @log_decorator(log_exception=True)
    def raise_error():
        raise ValueError("测试错误")

    try:
        raise_error()
        assert False, "应该抛出异常"
    except ValueError as e:
        assert str(e) == "测试错误"


# ============ 重试装饰器测试 ============

@runner.test("重试装饰器 - 第一次成功")
def test_retry_success_first():
    call_count = 0

    @retry(max_attempts=3, delay=0.1)
    def success_func():
        nonlocal call_count
        call_count += 1
        return "success"

    result = success_func()
    assert result == "success"
    assert call_count == 1, f"期望调用1次, 实际{call_count}次"


@runner.test("重试装饰器 - 失败后成功")
def test_retry_success_after_failures():
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
    assert call_count == 3, f"期望调用3次, 实际{call_count}次"


@runner.test("重试装饰器 - 全部失败")
def test_retry_all_fail():
    call_count = 0

    @retry(max_attempts=3, delay=0.1)
    def always_fail():
        nonlocal call_count
        call_count += 1
        raise ConnectionError("始终失败")

    try:
        always_fail()
        assert False, "应该抛出异常"
    except ConnectionError:
        pass

    assert call_count == 3, f"期望调用3次, 实际{call_count}次"


# ============ 计时装饰器测试 ============

@runner.test("计时装饰器 - 基本功能")
def test_timing_basic():
    @timing
    def slow_function():
        time.sleep(0.05)
        return "done"

    result = slow_function()
    assert result == "done"


@runner.test("计时装饰器 - 带参数")
def test_timing_with_args():
    @timing
    def compute(x, y):
        time.sleep(0.02)
        return x + y

    result = compute(10, 20)
    assert result == 30


# ============ 弃用装饰器测试 ============

@runner.test("弃用装饰器 - 基本功能")
def test_deprecated_basic():
    @deprecated("请使用 new_func")
    def old_func():
        return "old"

    result = old_func()
    assert result == "old"


# ============ 单例装饰器测试 ============

@runner.test("单例装饰器 - 相同实例")
def test_singleton_same_instance():
    @singleton
    class Database:
        def __init__(self):
            self.value = 0

    db1 = Database()
    db2 = Database()

    assert db1 is db2, "应该是同一个实例"


@runner.test("单例装饰器 - 共享状态")
def test_singleton_shared_state():
    @singleton
    class Config:
        def __init__(self):
            self.settings = {}

    config1 = Config()
    config1.settings["key"] = "value"

    config2 = Config()
    assert config2.settings["key"] == "value", "状态应该共享"


# ============ 组合测试 ============

@runner.test("组合装饰器")
def test_multiple_decorators():
    @timing
    @retry(max_attempts=2, delay=0.1)
    @log_decorator(log_level="DEBUG")
    def complex_operation():
        return "success"

    result = complex_operation()
    assert result == "success"


@runner.test("装饰器保留元数据")
def test_decorator_preserves_metadata():
    @log_decorator()
    @retry(max_attempts=3)
    @timing
    def my_function():
        """我的函数文档"""
        return 42

    assert my_function.__name__ == "my_function"
    assert my_function.__doc__ == "我的函数文档"


# 运行测试
if __name__ == "__main__":
    success = runner.run()
    sys.exit(0 if success else 1)
