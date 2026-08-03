"""
对比验证演示

模拟前后端对比验证流程
"""
import json
import random
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from gs2026.common.pipeline import FilterConfig, UnifiedPipeline


def generate_test_data(count=100):
    """生成测试数据"""
    industries = ['银行', '房地产', '电子', '医药', '汽车']
    
    stocks = []
    for i in range(count):
        industry = random.choice(industries)
        stocks.append({
            'code': f'{i+1:06d}',
            'name': f'股票{i+1}',
            'change_pct': round(random.uniform(-5, 10), 2),
            'price': round(random.uniform(10, 100), 2),
            'count': random.randint(0, 50),
            'window_count': random.randint(0, 20),
            'industry': industry,
            'main_net_amount': round(random.uniform(-1000, 5000), 2),
            'bond_code': f'11{random.randint(1000, 9999)}' if random.random() > 0.3 else None,
        })
    
    bonds = []
    for i in range(count):
        industry = random.choice(industries)
        bonds.append({
            'code': f'11{random.randint(1000, 9999)}',
            'name': f'债券{i+1}',
            'change_pct': round(random.uniform(-3, 8), 2),
            'price': round(random.uniform(100, 150), 2),
            'count': random.randint(0, 30),
            'window_count': random.randint(0, 15),
            'amount': round(random.uniform(1000, 10000), 2),
            'industry': industry,
            'is_green': random.random() < 0.1,  # 10%绿名单
        })
    
    return stocks, bonds


def simulate_frontend_filter(data, config_dict):
    """模拟前端过滤逻辑"""
    # 简化的前端逻辑
    result = data.copy()
    
    # 行业过滤
    if config_dict.get('industry'):
        result = [d for d in result if d.get('industry') == config_dict['industry']]
    
    # 前N区间次数
    n = config_dict.get('topn_window', 0)
    if n > 0:
        # 排除<=0，降序，取前N
        filtered = [d for d in result if d.get('window_count', 0) > 0]
        sorted_data = sorted(filtered, key=lambda x: x.get('window_count', 0), reverse=True)
        top_n = sorted_data[:n]
        codes = {d['code'] for d in top_n}
        result = [d for d in result if d['code'] in codes]
    
    return result


def run_comparison_test(test_name, config_dict):
    """运行对比测试"""
    print(f"\n{'='*60}")
    print(f"测试: {test_name}")
    print(f"{'='*60}")
    
    # 生成测试数据
    stocks, bonds = generate_test_data(100)
    
    # 模拟前端过滤
    frontend_stocks = simulate_frontend_filter(stocks, config_dict)
    
    # 后端过滤
    config = FilterConfig.from_dict({
        'stock_industry': config_dict.get('industry'),
        'stock_topn_window': config_dict.get('topn_window', 0),
    })
    pipeline = UnifiedPipeline(config)
    backend_stocks = pipeline.filter_stocks(stocks, monitor_performance=True)
    
    # 对比结果
    frontend_codes = {d['code'] for d in frontend_stocks}
    backend_codes = {d['code'] for d in backend_stocks}
    
    print(f"\n数据量:")
    print(f"  原始: {len(stocks)} 条")
    print(f"  前端: {len(frontend_stocks)} 条")
    print(f"  后端: {len(backend_stocks)} 条")
    
    # 性能
    stats = pipeline.get_performance_stats()
    if stats:
        print(f"\n性能:")
        print(f"  后端耗时: {stats[0]['elapsed_ms']:.2f}ms")
    
    # 对比
    if frontend_codes == backend_codes:
        print(f"\n✅ 结果一致 ({len(frontend_codes)} 条)")
        return True
    else:
        print(f"\n❌ 结果不一致")
        print(f"  仅前端: {frontend_codes - backend_codes}")
        print(f"  仅后端: {backend_codes - frontend_codes}")
        return False


def main():
    """主函数"""
    print("="*60)
    print("对比验证演示")
    print("="*60)
    
    tests = [
        ('无过滤', {}),
        ('仅前10区间次数', {'topn_window': 10}),
        ('仅银行行业', {'industry': '银行'}),
        ('银行+前5区间次数', {'industry': '银行', 'topn_window': 5}),
        ('仅前20区间次数', {'topn_window': 20}),
    ]
    
    passed = 0
    failed = 0
    
    for name, config in tests:
        if run_comparison_test(name, config):
            passed += 1
        else:
            failed += 1
    
    print(f"\n{'='*60}")
    print(f"验证完成: 通过 {passed}, 失败 {failed}")
    print(f"{'='*60}")
    
    if failed == 0:
        print("\n✅ 所有测试通过，可以进入阶段3")
    else:
        print(f"\n⚠️ 有 {failed} 个测试失败，需要修复")
    
    return failed == 0


if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)
