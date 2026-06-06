"""交易日工具 — 基于 data_jyrl 表计算执行日期范围

data_jyrl 表结构:
    trade_date    DATE    日期
    trade_status  INT     1=交易日, 0=非交易日

返回两种格式:
    get_start_end()  → ('2026-06-06', '2026-06-09')
    get_date_list()  → ['2026-06-06', '2026-06-07', '2026-06-08', '2026-06-09']
"""

from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy import create_engine

from gs2026.utils import config_util, log_util

logger = log_util.setup_logger("trading_day_util")
url = config_util.get_config("common.url")
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)


def get_prev_trading_day(ref_date: str = None) -> str:
    """获取 ref_date 之前最近的交易日（不含当天）"""
    if ref_date is None:
        ref_date = date.today().strftime('%Y-%m-%d')
    sql = (f"SELECT trade_date FROM data_jyrl "
           f"WHERE trade_date < '{ref_date}' AND trade_status = 1 "
           f"ORDER BY trade_date DESC LIMIT 1")
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    return str(df.iloc[0]['trade_date']) if not df.empty else ref_date


def get_next_trading_day(ref_date: str = None) -> str:
    """获取 ref_date 之后最近的交易日（不含当天）"""
    if ref_date is None:
        ref_date = date.today().strftime('%Y-%m-%d')
    sql = (f"SELECT trade_date FROM data_jyrl "
           f"WHERE trade_date > '{ref_date}' AND trade_status = 1 "
           f"ORDER BY trade_date ASC LIMIT 1")
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    return str(df.iloc[0]['trade_date']) if not df.empty else ref_date


def get_start_end(ref_date: str = None) -> tuple:
    """返回 (开始时间, 结束时间) 元组"""
    start = get_prev_trading_day(ref_date)
    end = get_next_trading_day(ref_date)
    logger.info(f"[交易日] start={start}, end={end}")
    return (start, end)


def get_date_list(ref_date: str = None) -> list:
    """返回区间内所有日历日期的list"""
    start_str, end_str = get_start_end(ref_date)
    start_dt = datetime.strptime(start_str, '%Y-%m-%d').date()
    end_dt = datetime.strptime(end_str, '%Y-%m-%d').date()
    result = []
    current = start_dt
    while current <= end_dt:
        result.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)
    logger.info(f"[交易日] date_list={result}")
    return result
