#!/usr/bin/env python3
"""
修复2026-04-27早盘上攻排行数据
直接修复09:30:03, 09:30:06, 09:30:09, 09:30:12的数据
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from datetime import datetime, time as dt_time
from gs2026.utils import redis_util
from gs2026.monitor.monitor_stock import calculate_top30_v3, attack_conditions
import pandas as pd
from loguru import logger

def fix_early_morning_data():
    date_str = "20260427"
    sssj_table = f"monitor_gp_sssj_{date_str}"
    
    # 初始化Redis
    redis_util.init_redis()
    
    # 获取最早时间戳
    earliest_time = redis_util.get_earliest_timestamp(sssj_table)
    if not earliest_time:
        logger.error("无法获取最早时间戳")
        return
    
    logger.info(f"最早时间戳: {earliest_time}")
    
    # 需要修复的时间点（9:30:00 - 9:30:15）
    fix_times = ["09:30:03", "09:30:06", "09:30:09", "09:30:12"]
    
    for time_full in fix_times:
        logger.info(f"修复时间点: {time_full}")
        
        # 加载当前时间数据
        df_now = redis_util.load_dataframe_by_key(f"{sssj_table}:{time_full}", use_compression=False)
        if df_now is None or df_now.empty:
            logger.warning(f"{time_full} 无数据，跳过")
            continue
        
        # 加载最早时间数据作为基准
        df_prev = redis_util.load_dataframe_by_key(f"{sssj_table}:{earliest_time}", use_compression=False)
        if df_prev is None or df_prev.empty:
            logger.warning(f"{earliest_time} 无数据，跳过")
            continue
        
        logger.info(f"  df_now: {len(df_now)}条, df_prev: {len(df_prev)}条")
        
        # 列名标准化
        rename_map = {}
        if 'stock_code' in df_now.columns and 'code' not in df_now.columns:
            rename_map['stock_code'] = 'code'
        if 'short_name' in df_now.columns and 'name' not in df_now.columns:
            rename_map['short_name'] = 'name'
        if rename_map:
            df_now = df_now.rename(columns=rename_map)
        
        rename_map_prev = {}
        if 'stock_code' in df_prev.columns and 'code' not in df_prev.columns:
            rename_map_prev['stock_code'] = 'code'
        if 'short_name' in df_prev.columns and 'name' not in df_prev.columns:
            rename_map_prev['short_name'] = 'name'
        if rename_map_prev:
            df_prev = df_prev.rename(columns=rename_map_prev)
        
        # 构建loop_start
        loop_start = datetime.strptime(f"{date_str} {time_full}", "%Y%m%d %H:%M:%S")
        
        # 重新计算top30
        top30_df = calculate_top30_v3(df_now, df_prev, loop_start)
        if top30_df.empty:
            logger.warning(f"{time_full} 计算结果为空")
            continue
        
        # 计算上攻条件
        result_df = attack_conditions(top30_df, rank_name='stock')
        
        # 保存到monitor_gp_top30表
        gp_top30_table = f"monitor_gp_top30_{date_str}"
        from gs2026.monitor.monitor_stock import save_dataframe, EXPIRE_SECONDS
        save_dataframe(result_df, gp_top30_table, time_full, EXPIRE_SECONDS)
        
        # 更新Redis累积排行
        redis_util.update_rank_redis(result_df, 'stock', date_str=date_str)
        
        logger.info(f"  完成修复: {len(result_df)}条数据")
    
    logger.info("修复完成")

if __name__ == "__main__":
    fix_early_morning_data()
