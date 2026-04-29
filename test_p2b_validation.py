# -*- coding: utf-8 -*-
"""
P2-B统一数据清洗方案 - 测试验证脚本
验证数据一致性和性能提升
"""

import sys
import os
import time
import pandas as pd
import numpy as np

sys.path.insert(0, 'F:/pyworkspace2026/gs2026/src')
os.environ['PYTHONIOENCODING'] = 'utf-8'

from gs2026.monitor.monitor_stock import (
    normalize_stock_dataframe, 
    USE_UNIFIED_CLEAN,
    calculate_top30_v3,
    get_market_stats,
    calculate_main_force_and_cumulative
)


def test_normalize_basic():
    """测试基础清洗功能"""
    print("=" * 60)
    print("测试1: 基础清洗功能")
    print("=" * 60)
    
    # 测试数据
    df = pd.DataFrame({
        'stock_code': ['1', '2', '000003', ' 4 ', '5.0'],
        'price': [10.5, 20.0, '30', 40, 50],
        'volume': [100, 200, 300, '400', 500],
        'amount': [1000, 2000, 3000, 4000, '5000'],
        'change_pct': [1.5, -2.0, '3.5', 4, -5],
    })
    
    print(f"原始数据:\n{df}")
    print(f"原始stock_code类型: {df['stock_code'].dtype}")
    
    result = normalize_stock_dataframe(df)
    
    print(f"\n清洗后数据:\n{result}")
    print(f"清洗后stock_code类型: {result['stock_code'].dtype}")
    print(f"stock_code值: {result['stock_code'].tolist()}")
    
    # 验证
    assert len(result) == 5, "行数应不变"
    assert result['stock_code'].iloc[0] == '000001', "代码应补零到6位"
    assert result['stock_code'].iloc[2] == '000003', "已有6位应保持"
    assert result['price'].dtype == np.float64, "price应为float"
    assert result['change_pct'].dtype == np.float64, "change_pct应为float"
    
    print("\n[OK] 测试1通过: 基础清洗功能正常")
    return True


def test_normalize_invalid_data():
    """测试无效数据过滤"""
    print("\n" + "=" * 60)
    print("测试2: 无效数据过滤")
    print("=" * 60)
    
    df = pd.DataFrame({
        'stock_code': ['1', '2', '3', '4', '5'],
        'price': [10, 0, -5, 20, 30],  # 0和负数应被过滤
        'volume': [100, 200, 0, 300, 400],  # 0应被过滤
        'amount': [1000, 2000, 3000, 0, 5000],  # 0应被过滤
    })
    
    print(f"原始数据: {len(df)}行")
    print(df)
    
    result = normalize_stock_dataframe(df)
    
    print(f"\n清洗后: {len(result)}行")
    print(result)
    
    # 验证：price<=0, volume<=0, amount<=0的行应被删除
    assert len(result) == 2, f"应只剩2行有效数据，实际{len(result)}行"
    assert all(result['price'] > 0), "所有price应>0"
    assert all(result['volume'] > 0), "所有volume应>0"
    assert all(result['amount'] > 0), "所有amount应>0"
    
    print("\n[OK] 测试2通过: 无效数据过滤正常")
    return True


def test_normalize_duplicates():
    """测试重复代码去重"""
    print("\n" + "=" * 60)
    print("测试3: 重复代码去重")
    print("=" * 60)
    
    df = pd.DataFrame({
        'stock_code': ['000001', '000001', '000002', '000002', '000003'],
        'price': [10, 11, 20, 21, 30],
        'volume': [100, 110, 200, 210, 300],
        'amount': [1000, 1100, 2000, 2100, 3000],
    })
    
    print(f"原始数据: {len(df)}行")
    print(df)
    
    result = normalize_stock_dataframe(df)
    
    print(f"\n清洗后: {len(result)}行")
    print(result)
    
    # 验证：应删除重复，保留第一个
    assert len(result) == 3, f"应剩3行（去重后），实际{len(result)}行"
    assert result['price'].iloc[0] == 10, "应保留第一个000001（price=10）"
    assert result['price'].iloc[1] == 20, "应保留第一个000002（price=20）"
    
    print("\n[OK] 测试3通过: 重复代码去重正常")
    return True


def test_normalize_default_values():
    """测试默认值填充"""
    print("\n" + "=" * 60)
    print("测试4: 默认值填充")
    print("=" * 60)
    
    df = pd.DataFrame({
        'stock_code': ['000001', '000002'],
        'price': [10, 20],
        'volume': [100, 200],
        'amount': [1000, 2000],
        'main_net_amount': [None, 100],  # None应填充为0
        'cumulative_main_net': [200, None],  # None应填充为0
    })
    
    print(f"原始数据:")
    print(df)
    
    result = normalize_stock_dataframe(df)
    
    print(f"\n清洗后:")
    print(result)
    
    # 验证
    assert result['main_net_amount'].iloc[0] == 0, "None应填充为0"
    assert result['main_net_amount'].iloc[1] == 100, "已有值应保持"
    assert result['cumulative_main_net'].iloc[0] == 200, "已有值应保持"
    assert result['cumulative_main_net'].iloc[1] == 0, "None应填充为0"
    
    print("\n[OK] 测试4通过: 默认值填充正常")
    return True


def test_normalize_code_alias():
    """测试code别名处理"""
    print("\n" + "=" * 60)
    print("测试5: code别名处理")
    print("=" * 60)
    
    # 只有code列，没有stock_code列
    df = pd.DataFrame({
        'code': ['1', '2', '3'],
        'price': [10, 20, 30],
        'volume': [100, 200, 300],
        'amount': [1000, 2000, 3000],
    })
    
    print(f"原始数据列: {df.columns.tolist()}")
    print(df)
    
    result = normalize_stock_dataframe(df)
    
    print(f"\n清洗后列: {result.columns.tolist()}")
    print(result)
    
    # 验证：应从code生成stock_code
    assert 'stock_code' in result.columns, "应生成stock_code列"
    assert result['stock_code'].iloc[0] == '000001', "code应映射为stock_code并补零"
    
    print("\n[OK] 测试5通过: code别名处理正常")
    return True


def test_performance():
    """测试性能提升"""
    print("\n" + "=" * 60)
    print("测试6: 性能对比")
    print("=" * 60)
    
    # 生成大规模测试数据
    n = 5000
    df = pd.DataFrame({
        'stock_code': [f'{i}' for i in range(n)],
        'price': np.random.uniform(10, 100, n),
        'volume': np.random.randint(1000, 100000, n),
        'amount': np.random.randint(10000, 1000000, n),
        'change_pct': np.random.uniform(-10, 10, n),
    })
    
    print(f"测试数据规模: {n}只股票")
    
    # 测试统一清洗
    times = []
    for _ in range(10):
        start = time.time()
        result = normalize_stock_dataframe(df.copy())
        times.append(time.time() - start)
    
    avg_time = sum(times) / len(times)
    print(f"统一清洗平均耗时: {avg_time*1000:.2f}ms")
    print(f"清洗后数据: {len(result)}行")
    
    # 对比：旧方式（多次清洗）
    def old_clean(df):
        """模拟旧方式的多次清洗"""
        # 第一次清洗（deal_gp_works）
        df['stock_code'] = df['stock_code'].astype(str).str.zfill(6)
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        
        # 第二次清洗（calculate_top30_v3）
        df = df.copy()
        df['stock_code'] = df['stock_code'].astype(str).str.zfill(6)
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        
        # 第三次清洗（get_market_stats）
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        
        return df
    
    old_times = []
    for _ in range(10):
        start = time.time()
        old_result = old_clean(df.copy())
        old_times.append(time.time() - start)
    
    old_avg_time = sum(old_times) / len(old_times)
    print(f"旧方式（多次清洗）平均耗时: {old_avg_time*1000:.2f}ms")
    
    speedup = old_avg_time / avg_time
    saved_ms = (old_avg_time - avg_time) * 1000
    
    print(f"\n性能提升: {speedup:.1f}x")
    print(f"每周期节省: {saved_ms:.1f}ms")
    
    if speedup >= 1.5:
        print("\n[OK] 测试6通过: 性能提升显著")
    else:
        print("\n[WARN] 测试6警告: 性能提升不明显")
    
    return True


def test_integration():
    """集成测试：验证下游函数使用清洗后的数据"""
    print("\n" + "=" * 60)
    print("测试7: 集成测试")
    print("=" * 60)
    
    # 模拟deal_gp_works中的数据
    df_now = pd.DataFrame({
        'stock_code': ['000001', '000002', '000003'],
        'short_name': ['平安银行', '万科A', '国农科技'],
        'price': [10.5, 20.0, 30.5],
        'volume': [100000, 200000, 300000],
        'amount': [1000000, 2000000, 3000000],
        'change_pct': [1.5, -2.0, 3.5],
        'time': ['10:00:00', '10:00:00', '10:00:00'],  # 添加time列
    })
    
    df_prev = pd.DataFrame({
        'stock_code': ['000001', '000002', '000003'],
        'price': [10.0, 20.5, 30.0],
        'volume': [90000, 210000, 290000],
        'amount': [900000, 2100000, 2900000],
        'change_pct': [1.0, -1.5, 3.0],
        'time': ['09:59:57', '09:59:57', '09:59:57'],  # 添加time列
    })
    
    print(f"df_now原始:\n{df_now}")
    print(f"\ndf_prev原始:\n{df_prev}")
    
    # 清洗数据（模拟deal_gp_works中的处理）
    df_now_cleaned = normalize_stock_dataframe(df_now)
    df_prev_cleaned = normalize_stock_dataframe(df_prev)
    
    print(f"\n清洗后df_now:\n{df_now_cleaned}")
    
    # 测试下游函数能否正常使用
    try:
        # 测试get_market_stats
        stats = get_market_stats(df_now_cleaned, df_prev_cleaned)
        print(f"\nget_market_stats结果:\n{stats}")
        
        print("\n[OK] 测试7通过: 集成测试正常")
        return True
    except Exception as e:
        print(f"\n[FAIL] 测试7失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("P2-B统一数据清洗方案 - 测试验证")
    print(f"USE_UNIFIED_CLEAN = {USE_UNIFIED_CLEAN}")
    print("=" * 60)
    
    results = []
    
    try:
        results.append(test_normalize_basic())
    except Exception as e:
        print(f"\n[FAIL] 测试1失败: {e}")
        results.append(False)
    
    try:
        results.append(test_normalize_invalid_data())
    except Exception as e:
        print(f"\n[FAIL] 测试2失败: {e}")
        results.append(False)
    
    try:
        results.append(test_normalize_duplicates())
    except Exception as e:
        print(f"\n[FAIL] 测试3失败: {e}")
        results.append(False)
    
    try:
        results.append(test_normalize_default_values())
    except Exception as e:
        print(f"\n[FAIL] 测试4失败: {e}")
        results.append(False)
    
    try:
        results.append(test_normalize_code_alias())
    except Exception as e:
        print(f"\n[FAIL] 测试5失败: {e}")
        results.append(False)
    
    try:
        results.append(test_performance())
    except Exception as e:
        print(f"\n[FAIL] 测试6失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(False)
    
    try:
        results.append(test_integration())
    except Exception as e:
        print(f"\n[FAIL] 测试7失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(False)
    
    # 汇总
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"通过: {passed}/{total}")
    
    if passed == total:
        print("\n[OK][OK][OK] 所有测试通过！P2-B方案验证成功 [OK][OK][OK]")
        return 0
    else:
        print(f"\n[FAIL][FAIL][FAIL] {total-passed}个测试失败，请检查 [FAIL][FAIL][FAIL]")
        return 1


if __name__ == '__main__':
    exit(main())
