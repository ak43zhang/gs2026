#!/usr/bin/env python3
"""验证2026-04-27早盘上攻排行修复结果 - 检查top30表"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from gs2026.utils import redis_util
from loguru import logger

def verify_fix():
    redis_util.init_redis()
    date_str = "20260427"
    table_name = f"monitor_gp_top30_{date_str}"
    
    # 检查各个时间点的数据
    check_times = ["09:30:03", "09:30:06", "09:30:09", "09:30:12"]
    
    logger.info("=" * 50)
    logger.info("验证2026-04-27早盘上攻排行修复结果")
    logger.info("=" * 50)
    
    for time_str in check_times:
        # 从Redis加载数据
        df = redis_util.load_dataframe_by_key(f"{table_name}:{time_str}", use_compression=False)
        
        if df is not None and not df.empty:
            logger.info(f"{time_str}: {len(df)}条数据")
            # 显示前5条
            for i, row in df.head(5).iterrows():
                code = row.get('code', row.get('stock_code', 'N/A'))
                name = row.get('name', row.get('short_name', 'N/A'))
                score = row.get('total_score', 'N/A')
                logger.info(f"  {i+1}. {code} {name} - 分数:{score}")
        else:
            logger.warning(f"{time_str}: 无数据")
    
    logger.info("=" * 50)
    logger.info("验证完成")

if __name__ == "__main__":
    verify_fix()
