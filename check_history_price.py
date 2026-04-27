#!/usr/bin/env python3
"""检查历史日期的价格数据来源"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from gs2026.utils import mysql_util, redis_util
from sqlalchemy import text
from loguru import logger

def check_history_price_source():
    mysql_tool = mysql_util.get_mysql_tool()
    
    logger.info("=" * 60)
    logger.info("检查历史日期价格数据来源")
    logger.info("=" * 60)
    
    # 1. 检查实时监控表是否存在
    logger.info("\n【1. 检查实时监控表】")
    for date in ['20260427', '20260428']:
        try:
            with mysql_tool.engine.connect() as conn:
                sql = f"SHOW TABLES LIKE 'monitor_gp_sssj_{date}'"
                result = conn.execute(text(sql)).fetchall()
                if result:
                    logger.info(f"monitor_gp_sssj_{date}: 存在")
                    # 检查数据量
                    count_sql = f"SELECT COUNT(*) FROM monitor_gp_sssj_{date}"
                    count_result = conn.execute(text(count_sql)).fetchone()
                    logger.info(f"  数据量: {count_result[0]}")
                else:
                    logger.warning(f"monitor_gp_sssj_{date}: 不存在")
        except Exception as e:
            logger.error(f"{date}: 查询失败 - {e}")
    
    # 2. 检查日K线表
    logger.info("\n【2. 检查日K线表】")
    try:
        with mysql_tool.engine.connect() as conn:
            for date in ['20260427', '20260428']:
                year = date[:4]
                table = f"data_gpsj_day_{date}"
                sql = f"SHOW TABLES LIKE '{table}'"
                result = conn.execute(text(sql)).fetchall()
                if result:
                    logger.info(f"{table}: 存在")
                    # 检查样本数据
                    sample_sql = f"SELECT COUNT(*) FROM {table}"
                    sample_result = conn.execute(text(sample_sql)).fetchone()
                    logger.info(f"  数据量: {sample_result[0]}")
                else:
                    logger.warning(f"{table}: 不存在")
    except Exception as e:
        logger.error(f"日K线表查询失败: {e}")
    
    # 3. 检查涨停分析表
    logger.info("\n【3. 检查涨停分析表】")
    try:
        with mysql_tool.engine.connect() as conn:
            sql = "SELECT trade_date, COUNT(*) as cnt FROM analysis_ztb_detail_2026 GROUP BY trade_date ORDER BY trade_date DESC LIMIT 5"
            results = conn.execute(text(sql)).fetchall()
            for row in results:
                logger.info(f"  {row[0]}: {row[1]} 条")
    except Exception as e:
        logger.error(f"涨停分析表查询失败: {e}")
    
    # 4. 检查Redis历史数据
    logger.info("\n【4. 检查Redis历史数据】")
    redis_util.init_redis()
    try:
        client = redis_util._get_redis_client()
        # 检查4月27日的时间戳列表
        ts_key = "monitor_gp_sssj_20260427:timestamps"
        ts_count = client.llen(ts_key)
        logger.info(f"4月27日时间戳数量: {ts_count}")
        
        if ts_count > 0:
            # 获取最近一个时间戳的数据
            latest_ts = client.lindex(ts_key, 0)
            logger.info(f"最近时间戳: {latest_ts}")
    except Exception as e:
        logger.error(f"Redis查询失败: {e}")

if __name__ == "__main__":
    check_history_price_source()
