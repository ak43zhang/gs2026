#!/usr/bin/env python3
"""检查Redis中4月27日和4月28日的涨停数据"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from gs2026.utils import redis_util
from loguru import logger

def check_redis_zt_data():
    redis_util.init_redis()
    
    logger.info("=" * 60)
    logger.info("检查Redis涨停数据")
    logger.info("=" * 60)
    
    # 检查4月27日
    logger.info("\n【4月27日】")
    zt_0427 = redis_util.get_zt_stocks_from_redis('20260427', 'stock')
    logger.info(f"涨停股票数量: {len(zt_0427) if zt_0427 else 0}")
    
    # 检查4月28日
    logger.info("\n【4月28日】")
    zt_0428 = redis_util.get_zt_stocks_from_redis('20260428', 'stock')
    logger.info(f"涨停股票数量: {len(zt_0428) if zt_0428 else 0}")
    
    # 检查实时数据表
    logger.info("\n【检查MySQL实时监控表】")
    from gs2026.utils import mysql_util
    mysql_tool = mysql_util.get_mysql_tool()
    
    try:
        with mysql_tool.engine.connect() as conn:
            # 4月27日
            sql_0427 = "SELECT COUNT(DISTINCT stock_code) as cnt FROM monitor_gp_sssj_20260427 WHERE is_zt = 1"
            result_0427 = conn.execute(sql_0427).fetchone()
            logger.info(f"4月27日实时监控表涨停: {result_0427[0] if result_0427 else 0}")
            
            # 4月28日
            sql_0428 = "SELECT COUNT(DISTINCT stock_code) as cnt FROM monitor_gp_sssj_20260428 WHERE is_zt = 1"
            result_0428 = conn.execute(sql_0428).fetchone()
            logger.info(f"4月28日实时监控表涨停: {result_0428[0] if result_0428 else 0}")
    except Exception as e:
        logger.error(f"MySQL查询失败: {e}")
    
    # 检查涨停分析表
    logger.info("\n【检查涨停分析表】")
    try:
        with mysql_tool.engine.connect() as conn:
            sql = "SELECT COUNT(*) as cnt FROM analysis_ztb_detail_2026 WHERE trade_date = '2026-04-27'"
            result = conn.execute(sql).fetchone()
            logger.info(f"4月27日涨停分析表: {result[0] if result else 0}")
    except Exception as e:
        logger.error(f"涨停分析表查询失败: {e}")

if __name__ == "__main__":
    check_redis_zt_data()
