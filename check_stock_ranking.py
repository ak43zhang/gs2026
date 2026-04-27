#!/usr/bin/env python3
"""检查股票上攻排行是否有债券代码字段"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from gs2026.utils import redis_util
from loguru import logger

def check_stock_ranking():
    redis_util.init_redis()
    
    date_str = "20260427"
    time_str = "09:56:57"
    
    logger.info("=" * 60)
    logger.info(f"检查股票上攻排行: {date_str} {time_str}")
    logger.info("=" * 60)
    
    # 获取股票上攻排行
    gp_table = f"monitor_gp_top30_{date_str}"
    gp_df = redis_util.load_dataframe_by_key(f"{gp_table}:{time_str}", use_compression=False)
    
    if gp_df is not None and not gp_df.empty:
        logger.info(f"股票排行数量: {len(gp_df)}")
        logger.info(f"字段列表: {gp_df.columns.tolist()}")
        
        # 检查是否有债券相关字段
        bond_fields = [col for col in gp_df.columns if 'bond' in col.lower()]
        if bond_fields:
            logger.info(f"债券相关字段: {bond_fields}")
        else:
            logger.warning("无债券相关字段")
        
        # 显示前5条数据
        logger.info("\n前5条数据:")
        logger.info(gp_df.head().to_string())
    else:
        logger.error("无法获取股票上攻排行")

if __name__ == "__main__":
    check_stock_ranking()
