"""
Pipeline单元测试

运行: python test_pipeline.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from gs2026.common.pipeline import (
    FilterConfig,
    UnifiedPipeline,
    IndustryFilter,
    TopNWindowFilter,
    TopNCountFilter,
)
from gs2026.common.pipeline.pipeline import IntersectionCalculator


def test_industry_filter():
    """测试行业过滤器"""
    print("\n测试: IndustryFilter")
    
    data = [
        {'code': '000001', 'industry': '银行', 'count': 10},
        {'code': '000002', 'industry': '房地产', 'count': 5},
        {'code': '000003', 'industry': '银行', 'count': 8},
    ]
    
    f = IndustryFilter('银行')
    result = f.apply(data)
    
    assert len(result) == 2, f"期望2条，实际{len(result)}条"
    assert all(d['industry'] == '银行' for d in result)
    print("✅ IndustryFilter 通过")


def test_topn_window_filter():
    """测试区间次数过滤器"""
    print("\n测试: TopNWindowFilter")
    
    data = [
        {'code': '000001', 'window_count': 10},
        {'code': '000002', 'window_count': 5},
        {'code': '000003', 'window_count': 8},
        {'code': '000004', 'window_count': 0},  # 应被排除
        {'code': '000005', 'window_count': 12},
    ]
    
    f = TopNWindowFilter(3)
    result = f.apply(data)
    
    # 应返回window_count最高的3条
    assert len(result) == 3, f"期望3条，实际{len(result)}条"
    codes = {d['code'] for d in result}
    assert '000005' in codes  # 12
    assert '000001' in codes  # 10
    assert '000003' in codes  # 8
    assert '000004' not in codes  # 0被排除
    print("✅ TopNWindowFilter 通过")


def test_pipeline_two_phase():
    """测试两阶段执行模型"""
    print("\n测试: UnifiedPipeline 两阶段执行")
    
    config = FilterConfig(
        stock_industry='银行',
        stock_topn_window=2,
    )
    
    data = [
        {'code': '000001', 'industry': '银行', 'window_count': 10},
        {'code': '000002', 'industry': '房地产', 'window_count': 15},  # 被行业过滤排除
        {'code': '000003', 'industry': '银行', 'window_count': 5},
        {'code': '000004', 'industry': '银行', 'window_count': 8},
    ]
    
    pipeline = UnifiedPipeline(config)
    result = pipeline.filter_stocks(data, monitor_performance=False)
    
    # 先行业过滤：只剩银行（000001, 000003, 000004）
    # 再取window_count前2：000001(10), 000004(8)
    assert len(result) == 2, f"期望2条，实际{len(result)}条"
    codes = {d['code'] for d in result}
    assert codes == {'000001', '000004'}
    print("✅ 两阶段执行 通过")


def test_intersection():
    """测试股债交集计算"""
    print("\n测试: IntersectionCalculator")
    
    stocks = [
        {'code': '000001', 'name': '平安银行', 'bond_code': '113001'},
        {'code': '000002', 'name': '万科A', 'bond_code': '113002'},
        {'code': '000003', 'name': '无债券股', 'bond_code': None},
    ]
    
    bonds = [
        {'code': '113001', 'name': '平安转债'},
        {'code': '113002', 'name': '万科转债'},
    ]
    
    result = IntersectionCalculator.calculate(stocks, bonds)
    
    assert len(result) == 2, f"期望2条交集，实际{len(result)}条"
    stock_codes = {r['stock_code'] for r in result}
    assert stock_codes == {'000001', '000002'}
    print("✅ IntersectionCalculator 通过")


def test_performance():
    """测试性能"""
    print("\n测试: 性能")
    
    import time
    
    # 生成测试数据
    data = [
        {
            'code': f'{i:06d}',
            'industry': ['银行', '房地产', '电子'][i % 3],
            'count': i % 20,
            'window_count': i % 10,
        }
        for i in range(1000)
    ]
    
    config = FilterConfig(
        stock_topn_sectors=2,
        stock_topn_window=10,
    )
    
    pipeline = UnifiedPipeline(config)
    
    # 预热
    for _ in range(10):
        pipeline.filter_stocks(data, monitor_performance=False)
    
    # 正式测试
    times = []
    for _ in range(100):
        start = time.perf_counter()
        pipeline.filter_stocks(data, monitor_performance=False)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    
    avg_time = sum(times) / len(times)
    max_time = max(times)
    
    print(f"  平均耗时: {avg_time:.2f}ms")
    print(f"  最大耗时: {max_time:.2f}ms")
    
    if avg_time < 100:
        print("✅ 性能达标 (<100ms)")
    else:
        print(f"⚠️ 性能待优化 (>{avg_time:.1f}ms)")


def run_all_tests():
    """运行所有测试"""
    print("="*60)
    print("Pipeline单元测试")
    print("="*60)
    
    tests = [
        test_industry_filter,
        test_topn_window_filter,
        test_pipeline_two_phase,
        test_intersection,
        test_performance,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} 失败: {e}")
            failed += 1
    
    print("\n" + "="*60)
    print(f"测试完成: 通过 {passed}, 失败 {failed}")
    print("="*60)
    
    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
