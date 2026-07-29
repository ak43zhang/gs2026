#!/usr/bin/env python3
"""
区间测算服务层 - 简化版（只使用MySQL）
基于 monitor_hy_top30_{date} 宽表，提供行业内最强/最弱聚合查询。

设计说明:
- 数据源: monitor_hy_top30_{date}（MySQL）
- 指标维度:
  - 'change_pct': 绝对涨幅（avg_change_pct）
  - 'delta_pct': 环比涨幅（delta_change_pct）
- 区间聚合: 累计值排序，取前10强/前10弱
"""
import logging

import pandas as pd
from sqlalchemy import text

from gs2026.utils import mysql_util

logger = logging.getLogger(__name__)


def _table_exists(table_name: str) -> bool:
    """检查表是否存在"""
    try:
        mysql_tool = mysql_util.get_mysql_tool()
        with mysql_tool.engine.connect() as conn:
            rows = pd.read_sql(
                text("SHOW TABLES LIKE :t"),
                conn, params={'t': table_name}
            )
        return not rows.empty
    except Exception as e:
        logger.warning(f"检查表存在失败 {table_name}: {e}")
        return False


def _has_column(table_name: str, column: str) -> bool:
    """检查表是否有某列（历史表兼容）"""
    try:
        mysql_tool = mysql_util.get_mysql_tool()
        with mysql_tool.engine.connect() as conn:
            rows = pd.read_sql(
                text(f"SHOW COLUMNS FROM {table_name} LIKE :c"),
                conn, params={'c': column}
            )
        return not rows.empty
    except Exception as e:
        logger.warning(f"检查列存在失败 {table_name}.{column}: {e}")
        return False


def get_available_dates(limit: int = 30) -> list:
    """获取有行业宽表数据的交易日列表（倒序）"""
    try:
        mysql_tool = mysql_util.get_mysql_tool()
        with mysql_tool.engine.connect() as conn:
            # 查询information_schema获取表名
            df = pd.read_sql(
                text("""
                    SELECT TABLE_NAME 
                    FROM information_schema.TABLES 
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME LIKE 'monitor_hy_top30_%'
                    ORDER BY TABLE_NAME DESC
                    LIMIT :limit
                """),
                conn, params={'limit': limit}
            )
        dates = [r['TABLE_NAME'].replace('monitor_hy_top30_', '') for r in df.to_dict('records')]
        return dates
    except Exception as e:
        logger.error(f"获取日期列表失败: {e}")
        return []


def get_timestamps(date: str) -> list:
    """获取某日所有tick时间戳"""
    table = f"monitor_hy_top30_{date}"
    if not _table_exists(table):
        return []
    try:
        mysql_tool = mysql_util.get_mysql_tool()
        with mysql_tool.engine.connect() as conn:
            rows = pd.read_sql(
                text(f"SELECT DISTINCT time FROM {table} ORDER BY time"),
                conn
            )
        return [str(t) for t in rows['time'].tolist()]
    except Exception as e:
        logger.error(f"获取时间戳失败 {date}: {e}")
        return []


def query_range_industry(date: str, start_time: str, end_time: str,
                         metric: str = 'change_pct') -> dict:
    """
    区间聚合：累计值排序，取前10强/前10弱
    【简化版】只使用MySQL，不走Redis
    """
    empty = {
        'strongest_rank': [], 'weakest_rank': [],
        'total_ticks': 0, 'time_range': [start_time, end_time]
    }
    
    # 调试日志
    logger.info(f"[DEBUG] query_range_industry called: date={date}, start={start_time}, end={end_time}, metric={metric}")
    
    table = f"monitor_hy_top30_{date}"
    if not _table_exists(table):
        logger.warning(f"表不存在: {table}")
        return empty

    # 确定查询字段
    value_col = 'delta_change_pct' if metric == 'delta_pct' else 'avg_change_pct'

    try:
        mysql_tool = mysql_util.get_mysql_tool()
        with mysql_tool.engine.connect() as conn:
            # 【优化】使用覆盖索引的聚合查询
            sql = f"""
                SELECT 
                    code,
                    MAX(name) as name,
                    SUM({value_col}) as cumulative_value,
                    AVG(total) as avg_stock_count
                FROM {table}
                WHERE time >= :s AND time <= :e
                GROUP BY code
                ORDER BY cumulative_value DESC
            """
            logger.info(f"[DEBUG] SQL: {sql}, params: s={start_time}, e={end_time}")
            
            df = pd.read_sql(
                text(sql),
                conn, params={'s': start_time, 'e': end_time}
            )
            
            logger.info(f"[DEBUG] Query returned {len(df)} rows")
    except Exception as e:
        logger.error(f"区间查询失败 {table}: {e}")
        return empty

    if df.empty:
        logger.warning(f"[DEBUG] Query returned empty result")
        return empty

    # 类型规整
    df['cumulative_value'] = pd.to_numeric(df['cumulative_value'], errors='coerce').fillna(0.0)
    df['avg_stock_count'] = pd.to_numeric(df['avg_stock_count'], errors='coerce').fillna(0).astype(int)
    df['code'] = df['code'].astype(str)

    # 取前10强/前10弱
    strongest_top10 = df.head(10).copy()
    weakest_top10 = df.tail(10).iloc[::-1].copy()  # 反转，让最负的排第一

    # 添加排名
    for i, row in strongest_top10.iterrows():
        strongest_top10.at[i, 'rank'] = int(i) + 1
    total = len(df)
    for i, row in weakest_top10.iterrows():
        weakest_top10.at[i, 'rank'] = total - 10 + int(i) + 1

    def _build_rank(df_rank):
        """构建排行结果"""
        result = []
        for _, row in df_rank.iterrows():
            result.append({
                'code': str(row['code']),
                'name': str(row['name']),
                'cumulative_value': round(float(row['cumulative_value']), 4),
                'avg_stock_count': int(row['avg_stock_count']),
                'rank': int(row['rank'])
            })
        return result

    return {
        'strongest_rank': _build_rank(strongest_top10),
        'weakest_rank': _build_rank(weakest_top10),
        'total_ticks': 0,  # MySQL聚合后不保留tick数
        'time_range': [start_time, end_time],
        'metric': metric,
        'source': 'mysql',
        'calc_method': 'cumulative'
    }


def get_industry_trend(date: str, code: str, start_time: str, end_time: str, metric: str = 'change_pct') -> dict:
    """某行业区间时序（画折线图）- 只走MySQL"""
    empty = {'times': [], 'values': [], 'ranks': []}
    
    table = f"monitor_hy_top30_{date}"
    if not _table_exists(table):
        return empty

    # 确定字段
    value_col = 'delta_change_pct' if metric == 'delta_pct' else 'avg_change_pct'
    rank_col = 'rank_by_delta_pct' if metric == 'delta_pct' else 'rank_by_change_pct'

    has_rank_col = _has_column(table, rank_col)

    try:
        mysql_tool = mysql_util.get_mysql_tool()
        with mysql_tool.engine.connect() as conn:
            df = pd.read_sql(
                text(f"""
                    SELECT time, {value_col}
                    {f', {rank_col}' if has_rank_col else ''}
                    FROM {table}
                    WHERE code = :c AND time >= :s AND time <= :e
                    ORDER BY time
                """),
                conn, params={'c': str(code), 's': start_time, 'e': end_time}
            )
    except Exception as e:
        logger.error(f"行业趋势查询失败 {table} {code}: {e}")
        return empty

    if df.empty:
        return empty

    df[value_col] = pd.to_numeric(df[value_col], errors='coerce').fillna(0.0)
    result = {
        'times': [str(t) for t in df['time'].tolist()],
        'values': [round(float(v), 4) for v in df[value_col].tolist()],
        'ranks': []
    }
    if has_rank_col:
        df[rank_col] = pd.to_numeric(df[rank_col], errors='coerce').fillna(0).astype(int)
        result['ranks'] = [int(v) for v in df[rank_col].tolist()]
    return result
