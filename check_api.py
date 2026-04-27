#!/usr/bin/env python3
"""检查股票上攻排行API返回的数据结构"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from gs2026.dashboard.services.data_service import DataService
from loguru import logger

def check_stock_ranking_api():
    ds = DataService()
    
    logger.info("=" * 60)
    logger.info("检查股票上攻排行API返回数据")
    logger.info("=" * 60)
    
    # 获取股票上攻排行
    data = ds.get_stock_ranking(limit=5, date='20260427', use_mysql=True)
    
    logger.info(f"返回数据条数: {len(data)}")
    
    if data:
        logger.info(f"第一条数据字段: {list(data[0].keys())}")
        logger.info(f"第一条数据: {data[0]}")
        
        # 检查是否有bond_code
        has_bond = any('bond' in str(k).lower() for k in data[0].keys())
        logger.info(f"是否有bond相关字段: {has_bond}")

if __name__ == "__main__":
    check_stock_ranking_api()
