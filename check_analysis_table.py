#!/usr/bin/env python3
"""检查涨停分析表是否有4月27日数据"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from gs2026.utils import mysql_util
from sqlalchemy import text
from loguru import logger

def check_analysis_table():
    mysql_tool = mysql_util.get_mysql_tool()
    
    logger.info("=" * 60)
    logger.info("检查涨停分析表")
    logger.info("=" * 60)
    
    try:
        with mysql_tool.engine.connect() as conn:
            # 检查表是否存在
            sql = "SHOW TABLES LIKE 'analysis_ztb_detail_2026'"
            result = conn.execute(text(sql)).fetchall()
            if result:
                logger.info("[OK] analysis_ztb_detail_2026 表存在")
                
                # 检查4月27日数据
                sql = "SELECT COUNT(*) as cnt FROM analysis_ztb_detail_2026 WHERE trade_date = '2026-04-27'"
                result = conn.execute(text(sql)).fetchone()
                logger.info(f"4月27日数据: {result[0]} 条")
                
                # 检查最近几天数据
                sql = """
                    SELECT trade_date, COUNT(*) as cnt 
                    FROM analysis_ztb_detail_2026 
                    GROUP BY trade_date 
                    ORDER BY trade_date DESC 
                    LIMIT 5
                """
                results = conn.execute(text(sql)).fetchall()
                logger.info("\n最近5天数据:")
                for row in results:
                    logger.info(f"  {row[0]}: {row[1]} 条")
            else:
                logger.error("[ERROR] analysis_ztb_detail_2026 表不存在")
    except Exception as e:
        logger.error(f"查询失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_analysis_table()
