# -*- coding: utf-8 -*-
"""
P2-D大盘统计优化 - 一致性测试
验证优化前后结果100%一致
"""

import sys
import os
import time
import pandas as pd
import numpy as np

sys.path.insert(0, 'F:/pyworkspace2026/gs2026/src')
os.environ['PYTHONIOENCODING'] = 'utf-8'

from gs2026.monitor.monitor_stock import (
    get_market_stats, 
    get_market_stats_v2,
    USE_OPTIMIZED_STATS
)


def generate_test_data(n=100, seed=42):
    """生成测试数据"""
    np.random.seed(seed)
    
    # 当前时刻数据
    df_now = pd.DataFrame({
        'code': [f'{i:06d}' for i in range(n)],
        'price': np.random.uniform(10, 100, n),
        'volume': np.random.randint(1000, 100000, n),
        'amount': np.random.randint(10000, 1000000, n),
        'change_pct': np.random.uniform(-10, 10, n),
        'time': ['10:00:00'] * n,
    })
    
    # 前时刻数据（部分股票缺失，模拟真实场景）
    n_prev = int(n * 0.95)  # 95%的股票前时刻存在
    df_prev = pd.DataFrame({
        'code': [f'{i:06d}' for i in range(n_prev)],
        'price': np.random.uniform(9, 99, n_prev),
        'volume': np.random.randint(900, 99000, n_prev),
        'amount': np.random.randint(9000, 990000, n_prev),
        'change_pct': np.random.uniform(-9, 9, n_prev),
        'time': ['09:59:57'] * n_prev,
    })
    
    return df_now, df_prev


def test_consistency():
    """测试新旧方案结果一致性"""
    print("=" * 60)
    print("P2-D一致性测试")
    print("=" * 60)
    
    df_now, df_prev = generate_test_data(n=1000)
    
    print(f"测试数据: {len(df_now)}只当前, {len(df_prev)}只前时刻")
    
    # 原方案（通过开关控制）
    import gs2026.monitor.monitor_stock as msm
    msm.USE_OPTIMIZED_STATS = False
    result_old = get_market_stats(df_now, df_prev)
    
    # 优化方案
    msm.USE_OPTIMIZED_STATS = True
    result_new = get_market_stats(df_now, df_prev)
    
    # 对比关键字段
    key_cols = [
        'cur_up', 'cur_down', 'cur_flat', 'cur_total',
        'cur_up_ratio', 'cur_down_ratio', 'cur_flat_ratio', 'cur_up_down_ratio',
        'min_up', 'min_down', 'min_flat', 'min_total',
        'min_up_ratio', 'min_down_ratio', 'min_flat_ratio', 'min_up_down_ratio'
    ]
    
    print("\n结果对比:")
    all_match = True
    for col in key_cols:
        old_val = result_old[col].iloc[0]
        new_val = result_new[col].iloc[0]
        
        # 处理NaN
        if pd.isna(old_val) and pd.isna(new_val):
            match = True
        elif pd.isna(old_val) or pd.isna(new_val):
            match = False
        else:
            match = np.isclose(old_val, new_val, rtol=1e-5)
        
        status = "OK" if match else "FAIL"
        print(f"  {col}: old={old_val}, new={new_val} [{status}]")
        
        if not match:
            all_match = False
    
    if all_match:
        print("\n[OK] 一致性测试通过: 所有字段100%一致")
        return True
    else:
        print("\n[FAIL] 一致性测试失败: 存在差异字段")
        return False


def test_performance():
    """测试性能提升"""
    print("\n" + "=" * 60)
    print("P2-D性能测试")
    print("=" * 60)
    
    df_now, df_prev = generate_test_data(n=5000)
    
    print(f"测试数据: {len(df_now)}只股票")
    
    import gs2026.monitor.monitor_stock as msm
    
    # 原方案
    msm.USE_OPTIMIZED_STATS = False
    times_old = []
    for _ in range(50):
        start = time.time()
        get_market_stats(df_now, df_prev)
        times_old.append(time.time() - start)
    avg_old = sum(times_old) / len(times_old)
    
    # 优化方案
    msm.USE_OPTIMIZED_STATS = True
    times_new = []
    for _ in range(50):
        start = time.time()
        get_market_stats(df_now, df_prev)
        times_new.append(time.time() - start)
    avg_new = sum(times_new) / len(times_new)
    
    speedup = avg_old / avg_new
    saved_ms = (avg_old - avg_new) * 1000
    
    print(f"\n性能对比:")
    print(f"  原方案: {avg_old*1000:.2f}ms")
    print(f"  优化后: {avg_new*1000:.2f}ms")
    print(f"  提升: {speedup:.1f}x")
    print(f"  节省: {saved_ms:.1f}ms")
    
    if speedup >= 1.5:
        print("\n[OK] 性能测试通过: 提升显著")
        return True
    else:
        print("\n[WARN] 性能提升不明显")
        return False


def test_edge_cases():
    """测试边界情况"""
    print("\n" + "=" * 60)
    print("P2-D边界测试")
    print("=" * 60)
    
    import gs2026.monitor.monitor_stock as msm
    msm.USE_OPTIMIZED_STATS = True
    
    tests = []
    
    # 测试1: 空数据
    print("\n测试1: 空数据")
    df_empty = pd.DataFrame({'code': [], 'change_pct': [], 'time': []})
    result = get_market_stats(df_empty, None)
    assert result['cur_total'].iloc[0] == 0
    print("  [OK] 空数据处理正常")
    tests.append(True)
    
    # 测试2: 全部平盘
    print("\n测试2: 全部平盘")
    df_flat = pd.DataFrame({
        'code': ['000001', '000002', '000003'],
        'change_pct': [0.0, 0.0, 0.0],
        'time': ['10:00:00'] * 3,
    })
    result = get_market_stats(df_flat, None)
    assert result['cur_flat'].iloc[0] == 3
    assert result['cur_up'].iloc[0] == 0
    print("  [OK] 全部平盘处理正常")
    tests.append(True)
    
    # 测试3: 全部上涨
    print("\n测试3: 全部上涨")
    df_up = pd.DataFrame({
        'code': ['000001', '000002', '000003'],
        'change_pct': [1.0, 2.0, 3.0],
        'time': ['10:00:00'] * 3,
    })
    result = get_market_stats(df_up, None)
    assert result['cur_up'].iloc[0] == 3
    assert result['cur_down'].iloc[0] == 0
    print("  [OK] 全部上涨处理正常")
    tests.append(True)
    
    # 测试4: 包含NaN
    print("\n测试4: 包含NaN")
    df_nan = pd.DataFrame({
        'code': ['000001', '000002', '000003'],
        'change_pct': [1.0, np.nan, 3.0],
        'time': ['10:00:00'] * 3,
    })
    result = get_market_stats(df_nan, None)
    assert result['cur_total'].iloc[0] == 2  # NaN被dropna
    print("  [OK] NaN处理正常（被dropna）")
    tests.append(True)
    
    if all(tests):
        print("\n[OK] 边界测试全部通过")
        return True
    else:
        print("\n[FAIL] 部分边界测试失败")
        return False


def main():
    """主测试"""
    print("\n" + "=" * 60)
    print("P2-D大盘统计优化 - 完整测试")
    print(f"USE_OPTIMIZED_STATS = {USE_OPTIMIZED_STATS}")
    print("=" * 60)
    
    results = []
    
    try:
        results.append(test_consistency())
    except Exception as e:
        print(f"[FAIL] 一致性测试异常: {e}")
        results.append(False)
    
    try:
        results.append(test_performance())
    except Exception as e:
        print(f"[FAIL] 性能测试异常: {e}")
        results.append(False)
    
    try:
        results.append(test_edge_cases())
    except Exception as e:
        print(f"[FAIL] 边界测试异常: {e}")
        results.append(False)
    
    # 汇总
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"通过: {passed}/{total}")
    
    if passed == total:
        print("\n[OK][OK][OK] P2-D优化验证成功 [OK][OK][OK]")
        return 0
    else:
        print(f"\n[FAIL] {total-passed}个测试失败")
        return 1


if __name__ == '__main__':
    exit(main())
