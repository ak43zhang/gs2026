#!/usr/bin/env python3
"""
区间测算服务层
基于 monitor_hy_top30_{date} 宽表（存全部行业，含 rank_by_change_pct 涨幅排名），
提供区间内行业最强/最弱聚合、时间戳、趋势等查询。

设计说明:
- 数据源: monitor_hy_top30_{date}（一表多用，上攻排行 final_score + 涨幅 rank_by_change_pct）
- 最强板块: 某tick rank_by_change_pct=1（涨幅最高）
- 最弱板块: 某tick rank_by_change_pct=最大（涨幅最低）
- 区间聚合: 统计各行业在区间内当选最强/最弱的次数
"""
import logging
from collections import Counter

import pandas as pd
from sqlalchemy import text

from gs2026.utils import mysql_util

logger = logging.getLogger(__name__)

# 小样本过滤：行业至少这么多只股票才纳入最强/最弱评选（去噪声）
MIN_TOTAL = 3


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
            rows = pd.read_sql(text("SHOW TABLES LIKE 'monitor_hy_top30_%'"), conn)
        if rows.empty:
            return []
        col = rows.columns[0]
        dates = [str(t).replace('monitor_hy_top30_', '') for t in rows[col].tolist()]
        dates = sorted(dates, reverse=True)
        return dates[:limit]
    except Exception as e:
        logger.error(f"获取可用日期失败: {e}")
        return []


def get_timestamps(date: str) -> list:
    """某日所有tick时间戳（升序，供区间双滑块）"""
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
    区间聚合：统计每个行业当选"最强/最弱"的次数

    Args:
        date: 日期 YYYYMMDD
        start_time: 起始时间 HH:MM:SS
        end_time: 结束时间 HH:MM:SS
        metric: 指标维度（预留），当前仅支持 change_pct

    Returns:
        dict: strongest_rank / weakest_rank / total_ticks / time_range
    """
    empty = {
        'strongest_rank': [], 'weakest_rank': [],
        'total_ticks': 0, 'time_range': [start_time, end_time]
    }
    table = f"monitor_hy_top30_{date}"
    if not _table_exists(table):
        logger.warning(f"表不存在: {table}")
        return empty

    # 历史表兼容：无 rank_by_change_pct 列则降级（用 avg_change_pct 实时排序）
    has_rank_col = _has_column(table, 'rank_by_change_pct')

    try:
        mysql_tool = mysql_util.get_mysql_tool()
        with mysql_tool.engine.connect() as conn:
            # 拉区间全部行业数据（含total用于过滤小样本）
            df = pd.read_sql(
                text(f"""
                    SELECT time, code, name, avg_change_pct, total
                    {', rank_by_change_pct' if has_rank_col else ''}
                    FROM {table}
                    WHERE time >= :s AND time <= :e
                """),
                conn, params={'s': start_time, 'e': end_time}
            )
    except Exception as e:
        logger.error(f"区间查询失败 {table}: {e}")
        return empty

    if df.empty:
        return empty

    # 类型规整
    df['avg_change_pct'] = pd.to_numeric(df['avg_change_pct'], errors='coerce').fillna(0.0)
    df['total'] = pd.to_numeric(df['total'], errors='coerce').fillna(0).astype(int)
    df['code'] = df['code'].astype(str)

    # 小样本过滤（去噪声）
    df_valid = df[df['total'] >= MIN_TOTAL].copy()
    if df_valid.empty:
        df_valid = df.copy()

    strongest_counter = Counter()
    weakest_counter = Counter()
    strongest_pct_sum = {}
    weakest_pct_sum = {}
    name_map = {}

    # 按tick分组，每tick取涨幅最强(max)和最弱(min)
    for tick, g in df_valid.groupby('time'):
        if g.empty:
            continue
        # 最强 = 涨幅最大
        s_row = g.loc[g['avg_change_pct'].idxmax()]
        # 最弱 = 涨幅最小
        w_row = g.loc[g['avg_change_pct'].idxmin()]

        sc = str(s_row['code'])
        strongest_counter[sc] += 1
        strongest_pct_sum[sc] = strongest_pct_sum.get(sc, 0.0) + float(s_row['avg_change_pct'])
        name_map[sc] = s_row['name']

        wc = str(w_row['code'])
        weakest_counter[wc] += 1
        weakest_pct_sum[wc] = weakest_pct_sum.get(wc, 0.0) + float(w_row['avg_change_pct'])
        name_map[wc] = w_row['name']

    total_ticks = df_valid['time'].nunique()

    def _build_rank(counter, pct_sum):
        result = []
        for code, cnt in counter.most_common(10):
            result.append({
                'code': code,
                'name': name_map.get(code, code),
                'count': cnt,
                'ratio': round(cnt / total_ticks, 4) if total_ticks else 0,
                'avg_change_pct': round(pct_sum[code] / cnt, 4) if cnt else 0
            })
        return result

    return {
        'strongest_rank': _build_rank(strongest_counter, strongest_pct_sum),
        'weakest_rank': _build_rank(weakest_counter, weakest_pct_sum),
        'total_ticks': int(total_ticks),
        'time_range': [start_time, end_time]
    }


def get_industry_trend(date: str, code: str, start_time: str, end_time: str) -> dict:
    """某行业区间涨幅时序（画折线图）"""
    empty = {'times': [], 'change_pcts': [], 'ranks': []}
    table = f"monitor_hy_top30_{date}"
    if not _table_exists(table):
        return empty

    has_rank_col = _has_column(table, 'rank_by_change_pct')
    try:
        mysql_tool = mysql_util.get_mysql_tool()
        with mysql_tool.engine.connect() as conn:
            df = pd.read_sql(
                text(f"""
                    SELECT time, avg_change_pct
                    {', rank_by_change_pct' if has_rank_col else ''}
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

    df['avg_change_pct'] = pd.to_numeric(df['avg_change_pct'], errors='coerce').fillna(0.0)
    result = {
        'times': [str(t) for t in df['time'].tolist()],
        'change_pcts': [round(float(v), 4) for v in df['avg_change_pct'].tolist()],
        'ranks': []
    }
    if has_rank_col:
        df['rank_by_change_pct'] = pd.to_numeric(df['rank_by_change_pct'], errors='coerce').fillna(0).astype(int)
        result['ranks'] = [int(v) for v in df['rank_by_change_pct'].tolist()]
    return result
