#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通达信风险数据分析 - 隔夜超短风险评估
分析 adata.sentiment.mine.mine_clearance_tdx 返回的数据
"""

import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import pandas as pd
import adata
from datetime import datetime

# 测试获取数据
stock_code = "000001"  # 平安银行作为示例
print(f"正在获取股票 {stock_code} 的通达信风险数据...")
print("=" * 80)

try:
    df = adata.sentiment.mine.mine_clearance_tdx(stock_code=stock_code)
    
    print(f"\n数据形状: {df.shape}")
    print(f"列名: {list(df.columns)}")
    print(f"\n数据类型:")
    print(df.dtypes)
    print(f"\n前5条数据:")
    print(df.head().to_string())
    print(f"\n数据描述统计:")
    print(df.describe().to_string())
    
    # 保存样本数据
    df.to_csv('mine_clearance_tdx_sample.csv', index=False, encoding='utf-8-sig')
    print(f"\n样本数据已保存到: mine_clearance_tdx_sample.csv")
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
