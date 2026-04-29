# -*- coding: utf-8 -*-
"""
向量化优化测试脚本
验证第一阶段优化效果
"""

import sys
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'

from pathlib import Path
import time
import pandas as pd
import numpy as np

# 添加项目路径
project_root = Path(__file__).parent
src_root = project_root / 'src'
if str(src_root) not in sys.path:
    sys.path.insert(0, str(src_root))

from gs2026.monitor.monitor_stock import (
    calc_is_zt, 
    calculate_participation_ratio,
    classify_main_force_behavior
)
from gs2026.monitor.vectorized_funcs import (
    calc_is_zt_vectorized,
    calculate_participation_ratio_vectorized
)
from datetime import time as dt_time


def test_calc_is_zt():
    """测试涨停判断向量化"""
    print("\n" + "="*60)
    print("测试1: 涨停判断向量化")
    print("="*60)
    
    # 创建测试数据
    n = 5000
    test_df = pd.DataFrame({
        'stock_code': [f'{i:06d}' for i in range(n)],
        'change_pct': np.random.uniform(-10, 20, n),
        'short_name': ['平安银行'] * n
    })
    
    # 测试apply方式
    print("\n1.1 apply方式:")
    start = time.time()
    for _ in range(10):
        result_apply = test_df.apply(
            lambda row: calc_is_zt(
                row['change_pct'],
                row['stock_code'],
                row['short_name']
            ),
            axis=1
        )
    time_apply = time.time() - start
    print(f"   耗时: {time_apply:.3f}s")
    
    # 测试向量化方式
    print("\n1.2 向量化方式:")
    start = time.time()
    for _ in range(10):
        result_vec = calc_is_zt_vectorized(test_df)
    time_vec = time.time() - start
    print(f"   耗时: {time_vec:.3f}s")
    
    # 验证结果一致
    print("\n1.3 结果验证:")
    if (result_apply.values == result_vec.values).all():
        print("   ✅ 结果一致")
    else:
        print("   ❌ 结果不一致！")
        diff = (result_apply != result_vec).sum()
        print(f"   差异数量: {diff}")
    
    # 计算提升
    speedup = time_apply / time_vec
    print(f"\n1.4 性能提升: {speedup:.1f}倍")
    print(f"   节省时间: {time_apply - time_vec:.3f}s")
    
    return speedup


def test_participation_ratio():
    """测试参与系数向量化"""
    print("\n" + "="*60)
    print("测试2: 参与系数向量化")
    print("="*60)
    
    # 创建测试数据
    n = 5000
    delta_amount = pd.Series(np.random.uniform(0, 3000000, n))
    
    # 测试apply方式
    print("\n2.1 apply方式:")
    start = time.time()
    for _ in range(100):
        result_apply = delta_amount.apply(calculate_participation_ratio)
    time_apply = time.time() - start
    print(f"   耗时: {time_apply:.3f}s")
    
    # 测试向量化方式
    print("\n2.2 向量化方式:")
    start = time.time()
    for _ in range(100):
        result_vec = calculate_participation_ratio_vectorized(delta_amount)
    time_vec = time.time() - start
    print(f"   耗时: {time_vec:.3f}s")
    
    # 验证结果一致
    print("\n2.3 结果验证:")
    # 使用近似相等（浮点数精度）
    if np.allclose(result_apply.values, result_vec.values, rtol=1e-5):
        print("   ✅ 结果一致")
    else:
        print("   ❌ 结果不一致！")
        diff = np.abs(result_apply - result_vec).max()
        print(f"   最大差异: {diff}")
    
    # 计算提升
    speedup = time_apply / time_vec
    print(f"\n2.4 性能提升: {speedup:.1f}倍")
    print(f"   节省时间: {time_apply - time_vec:.3f}s")
    
    return speedup


def test_combined():
    """测试综合效果"""
    print("\n" + "="*60)
    print("测试3: 综合效果评估")
    print("="*60)
    
    # 模拟一个周期的处理时间
    n = 5000
    
    # 原始方式
    print("\n3.1 原始apply方式:")
    start = time.time()
    for _ in range(10):
        # 涨停判断
        test_df = pd.DataFrame({
            'stock_code': [f'{i:06d}' for i in range(n)],
            'change_pct': np.random.uniform(-10, 20, n),
            'short_name': ['Test'] * n
        })
        test_df.apply(lambda row: calc_is_zt(row['change_pct'], row['stock_code'], row['short_name']), axis=1)
        
        # 参与系数
        delta_amount = pd.Series(np.random.uniform(0, 3000000, n))
        delta_amount.apply(calculate_participation_ratio)
    time_original = time.time() - start
    print(f"   10个周期耗时: {time_original:.3f}s")
    print(f"   单个周期: {time_original/10:.3f}s")
    
    # 向量化方式
    print("\n3.2 向量化方式:")
    start = time.time()
    for _ in range(10):
        # 涨停判断
        test_df = pd.DataFrame({
            'stock_code': [f'{i:06d}' for i in range(n)],
            'change_pct': np.random.uniform(-10, 20, n),
            'short_name': ['Test'] * n
        })
        calc_is_zt_vectorized(test_df)
        
        # 参与系数
        delta_amount = pd.Series(np.random.uniform(0, 3000000, n))
        calculate_participation_ratio_vectorized(delta_amount)
    time_vectorized = time.time() - start
    print(f"   10个周期耗时: {time_vectorized:.3f}s")
    print(f"   单个周期: {time_vectorized/10:.3f}s")
    
    # 计算提升
    speedup = time_original / time_vectorized
    time_saved = time_original - time_vectorized
    print(f"\n3.3 综合提升: {speedup:.1f}倍")
    print(f"   节省时间: {time_saved:.3f}s")
    print(f"   每个周期节省: {time_saved/10:.3f}s")
    
    return speedup, time_saved


def main():
    """主函数"""
    print("="*60)
    print("向量化优化测试 - 第一阶段")
    print("="*60)
    print("\n测试环境:")
    print(f"   股票数量: 5000只")
    print(f"   测试次数: 10-100次")
    
    # 运行测试
    speedup1 = test_calc_is_zt()
    speedup2 = test_participation_ratio()
    speedup3, time_saved = test_combined()
    
    # 总结
    print("\n" + "="*60)
    print("测试结果总结")
    print("="*60)
    print(f"\n1. 涨停判断向量化: {speedup1:.1f}倍提升")
    print(f"2. 参与系数向量化: {speedup2:.1f}倍提升")
    print(f"3. 综合效果: {speedup3:.1f}倍提升")
    print(f"\n每个周期预计节省: {time_saved/10*1000:.1f}ms")
    print(f"\n✅ 第一阶段向量化优化实施完成！")
    print("="*60)


if __name__ == '__main__':
    main()
