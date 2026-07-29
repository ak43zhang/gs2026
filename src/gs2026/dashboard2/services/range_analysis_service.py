#!/usr/bin/env python3
"""
区间测算服务层
基于 monitor_hy_top30_{date} 宽表（一表多用），提供行业内最强/最弱聚合查询。

设计说明:
- 数据源: monitor_hy_top30_{date}
- 指标维度:
  - 'change_pct': 绝对涨幅（avg_change_pct）
  - 'delta_pct': 环比涨幅（delta_change_pct，与上一tick相比）
- 最强板块: 某tick排名=1（该指标最大）
- 最弱板块: 某tick排名=最大（该指标最小）
- 区间聚合: 统计各行业在区间内当选"最强/最弱"的次数
"""
import logging
from collections import Counter

import pandas as pd
from sqlalchemy import text

from gs2026.utils import mysql_util, redis_util

logger = logging.getLogger(__name__)

# 小样本过滤：行业至少这么多只股票才纳入评选（去噪声）
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
        metric: 指标维度
                'change_pct' = 绝对涨幅（avg_change_pct）
                'delta_pct' = 环比涨幅（delta_change_pct）

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

    # 确定查询字段
    if metric == 'delta_pct':
        value_col = 'delta_change_pct'
        # 【Redis优先】先尝试从Redis读取
        redis_result = _query_range_from_redis(date, start_time, end_time)
        if redis_result.get('strongest_rank') or redis_result.get('weakest_rank'):
            logger.info(f"Redis命中: {date} {start_time}-{end_time}")
            return redis_result
        # Redis无数据，降级到MySQL
        logger.info(f"Redis未命中，降级到MySQL: {date}")
    else:
        value_col = 'avg_change_pct'

    try:
        mysql_tool = mysql_util.get_mysql_tool()
        with mysql_tool.engine.connect() as conn:
            # 拉区间全部行业数据
            if metric == 'delta_pct' and has_col:
                df = pd.read_sql(
                    text(f"""
                        SELECT time, code, name, {value_col}, total
                        FROM {table}
                        WHERE time >= :s AND time <= :e
                    """),
                    conn, params={'s': start_time, 'e': end_time}
                )
            else:
                df = pd.read_sql(
                    text(f"""
                        SELECT time, code, name, {value_col}, total
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
    df[value_col] = pd.to_numeric(df[value_col], errors='coerce').fillna(0.0)
    df['total'] = pd.to_numeric(df['total'], errors='coerce').fillna(0).astype(int)
    df['code'] = df['code'].astype(str)

    # 小样本过滤（去噪声）
    df_valid = df[df['total'] >= MIN_TOTAL].copy()
    if df_valid.empty:
        df_valid = df.copy()

    # 【C方案】累计Δ排行：区间内各指标累计值排序
    # 按行业分组，计算区间内累计值
    industry_stats = df_valid.groupby(['code', 'name']).agg({
        value_col: 'sum',  # 累计Δ
        'total': 'mean'    # 平均股票数（用于显示）
    }).reset_index()
    
    industry_stats.columns = ['code', 'name', 'cumulative_value', 'avg_stock_count']
    industry_stats = industry_stats.sort_values('cumulative_value', ascending=False)
    
    # 最强前10 = 累计Δ最大的
    strongest_top10 = industry_stats.head(10)
    # 最弱前10 = 累计Δ最小的（最负的）
    weakest_top10 = industry_stats.tail(10).iloc[::-1]  # 反转，让最负的排第一

    total_ticks = df_valid['time'].nunique()

    def _build_cumulative_rank(df_rank):
        """构建累计排行结果"""
        result = []
        for i, row in df_rank.iterrows():
            result.append({
                'code': str(row['code']),
                'name': str(row['name']),
                'cumulative_value': round(float(row['cumulative_value']), 4),
                'avg_stock_count': round(float(row['avg_stock_count']), 1),
                'rank': int(industry_stats.index.get_loc(i)) + 1 if i in industry_stats.index else 0
            })
        return result

    return {
        'strongest_rank': _build_cumulative_rank(strongest_top10),
        'weakest_rank': _build_cumulative_rank(weakest_top10),
        'total_ticks': int(total_ticks),
        'time_range': [start_time, end_time],
        'metric': metric,
        'calc_method': 'cumulative'  # 标识计算方法
    }


def _query_range_from_redis(date: str, start_time: str, end_time: str) -> dict:
    """
    【Redis优先】从Redis读取区间内所有tick的环比数据，计算累计排行
    
    Redis结构：
    - monitor_hy_top30_{date}:delta:{time} → {code: delta_pct}
    - monitor_hy_top30_{date}:delta_times → [time1, time2, ...]
    - monitor_hy_top30_{date}:ind_names → {code: name}
    """
    empty = {
        'strongest_rank': [], 'weakest_rank': [],
        'total_ticks': 0, 'time_range': [start_time, end_time],
        'metric': 'delta_pct', 'source': 'redis'
    }
    
    try:
        client = redis_util._get_redis_client()
        
        # 1. 获取tick列表
        ts_key = f"monitor_hy_top30_{date}:delta_times"
        all_times = client.lrange(ts_key, 0, -1)
        if not all_times:
            return empty
        
        times = [t.decode() if isinstance(t, bytes) else t for t in all_times]
        times = [t for t in times if start_time <= t <= end_time]
        if not times:
            return empty
        
        # 2. 【优化】使用pipeline批量读取所有tick数据
        pipe = client.pipeline()
        for t in times:
            hash_key = f"monitor_hy_top30_{date}:delta:{t}"
            pipe.hgetall(hash_key)
        
        # 一次性执行所有命令
        results = pipe.execute()
        
        # 3. 解析数据
        all_data = {}  # {code: [delta1, delta2, ...]}
        for raw in results:
            if raw:
                for code_b, val_b in raw.items():
                    code = code_b.decode() if isinstance(code_b, bytes) else str(code_b)
                    val = val_b.decode() if isinstance(val_b, bytes) else str(val_b)
                    code = str(code).strip()
                    if code not in all_data:
                        all_data[code] = []
                    all_data[code].append(float(val))
        
        if not all_data:
            return empty
        
        # 4. 获取行业名称
        name_key = f"monitor_hy_top30_{date}:ind_names"
        name_map = {}
        try:
            raw_names = client.hgetall(name_key)
            if raw_names:
                for code_b, name_b in raw_names.items():
                    code = code_b.decode() if isinstance(code_b, bytes) else str(code_b)
                    name = name_b.decode() if isinstance(name_b, bytes) else str(name_b)
                    name_map[str(code).strip()] = name
        except:
            pass
        
        # 5. 计算累计Δ
        industry_stats = []
        for code, deltas in all_data.items():
            cumulative = sum(deltas)
            industry_stats.append({
                'code': code,
                'name': name_map.get(code, code),
                'cumulative_value': cumulative,
                'avg_stock_count': 0  # Redis不存股票数
            })
        
        # 6. 排序
        industry_stats.sort(key=lambda x: x['cumulative_value'], reverse=True)
        
        # 7. 取前10强/前10弱
        strongest = industry_stats[:10]
        weakest = industry_stats[-10:][::-1]  # 最负的排前面
        
        # 8. 添加排名
        for i, item in enumerate(strongest):
            item['rank'] = i + 1
        for i, item in enumerate(weakest):
            item['rank'] = len(industry_stats) - len(weakest) + i + 1
        
        return {
            'strongest_rank': strongest,
            'weakest_rank': weakest,
            'total_ticks': len(times),
            'time_range': [start_time, end_time],
            'metric': 'delta_pct',
            'source': 'redis',
            'calc_method': 'cumulative'
        }
        
    except Exception as e:
        logger.warning(f"Redis查询失败: {e}")
        return empty


def get_industry_trend(date: str, code: str, start_time: str, end_time: str, metric: str = 'change_pct') -> dict:
    """某行业区间时序（画折线图）"""
    empty = {'times': [], 'values': [], 'ranks': []}
    
    # 【Redis优先】环比数据
    if metric == 'delta_pct':
        redis_trend = _get_trend_from_redis(date, code, start_time, end_time)
        if redis_trend['times']:
            return redis_trend
        # 降级到MySQL
    
    # MySQL查询（绝对涨幅或Redis未命中）
    table = f"monitor_hy_top30_{date}"
    if not _table_exists(table):
        return empty

    # 确定字段
    if metric == 'delta_pct':
        value_col = 'delta_change_pct'
        rank_col = 'rank_by_delta_pct'
    else:
        value_col = 'avg_change_pct'
        rank_col = 'rank_by_change_pct'

    has_rank_col = _has_column(table, rank_col)
    has_value_col = _has_column(table, value_col)
    
    if not has_value_col:
        return empty

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


def _get_trend_from_redis(date: str, code: str, start_time: str, end_time: str) -> dict:
    """【Redis优先】从Redis读取某行业区间趋势 - 优化版"""
    empty = {'times': [], 'values': [], 'ranks': [], 'source': 'redis'}
    
    try:
        client = redis_util._get_redis_client()
        
        # 1. 获取tick列表
        ts_key = f"monitor_hy_top30_{date}:delta_times"
        all_times = client.lrange(ts_key, 0, -1)
        if not all_times:
            return empty
        
        times = [t.decode() if isinstance(t, bytes) else t for t in all_times]
        times = [t for t in times if start_time <= t <= end_time]
        
        # 2. 【优化】使用pipeline批量读取
        pipe = client.pipeline()
        for t in times:
            hash_key = f"monitor_hy_top30_{date}:delta:{t}"
            pipe.hget(hash_key, code)
        
        results = pipe.execute()
        
        # 3. 解析数据
        values = []
        for val in results:
            if val:
                v = val.decode() if isinstance(val, bytes) else val
                values.append(float(v))
            else:
                values.append(0.0)
        
        return {
            'times': times,
            'values': [round(v, 4) for v in values],
            'ranks': [],
            'source': 'redis'
        }
    except Exception as e:
        logger.warning(f"Redis趋势查询失败: {e}")
        return empty
