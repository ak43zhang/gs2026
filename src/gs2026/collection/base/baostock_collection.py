"""
股票日数据收集
"""
import time
import warnings
from typing import Optional

import baostock as bs
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning
from loguru import logger

from gs2026.utils import mysql_util, config_util, string_enum
from gs2026.utils.pandas_display_config import set_pandas_display_options

warnings.filterwarnings("ignore", category=SAWarning)

set_pandas_display_options()

url = config_util.get_config("common.url")

engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()
mysql_tool = mysql_util.MysqlTool(url)


def get_multiple_stocks(stock_code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """
    获取多只股票历史K线数据

    Args:
        stock_code: 股票代码
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        股票数据DataFrame或None
    """
    # 根据股票代码确定市场前缀
    market = "sh." if stock_code.startswith(("6", "9")) else "sz."

    # 获取单只股票历史K线（后复权）
    rs = bs.query_history_k_data_plus(
        code=market + stock_code,
        fields="code,date,open,close,high,low,volume,amount,pctChg,turn,preclose",
        start_date=start_date,
        end_date=end_date,
        frequency="d",
        adjustflag="3"
    )

    # 转换为DataFrame
    data_list = []
    while (rs.error_code == '0') and rs.next():
        data_list.append(rs.get_row_data())
    df = pd.DataFrame(data_list, columns=rs.fields)
    if df.empty:
        logger.warning(f"stock_update>>>>>>代码：{stock_code}无值")
        return None
    else:
        df["stock_code"] = df['code'].apply(lambda x: f'{x.split(".")[1]}')
        df["trade_time"] = df['date'].apply(lambda x: f'{x + " 00:00:00"}')
        df['trade_date'] = df['date']
        df['open'] = df['open'].round(2).astype(float)
        df['close'] = df['close'].round(2).astype(float)
        df['high'] = df['high'].round(2).astype(float)
        df['low'] = df['low'].round(2).astype(float)
        df['volume'] = (df['volume'].replace(r'^\s*$', '0', regex=True).astype(float) // 100) * 100
        df['amount'] = df['amount'].replace(r'^\s*$', '0', regex=True).astype(float).round(2)
        df['change_pct'] = df['pctChg'].replace(r'^\s*$', '0', regex=True).astype(float).round(2)
        df['change'] = (df['close'].astype(float) - df['preclose'].astype(float)).astype(float).round(2)
        df['turnover_ratio'] = df['turn'].replace(r'^\s*$', '0', regex=True).astype(float).round(2)
        df['pre_close'] = df['preclose'].round(2).astype(float)
        result_df = df[["stock_code", "trade_time", 'trade_date', 'open', 'close', 'high', 'low',
                        'volume', 'amount', 'change_pct', 'change', 'turnover_ratio', 'pre_close']]
        return result_df


def stock_update(start_date: str, end_date: str) -> None:
    """
    更新股票数据

    Args:
        start_date: 开始日期
        end_date: 结束日期
    """
    table_name = f'data_gpsj_day_' + start_date.replace("-", "")
    if mysql_tool.check_table_exists(table_name):
        mysql_tool.drop_mysql_table(table_name)

    sql = string_enum.AG_STOCK_SQL5
    code_df = pd.read_sql(sql, con=con)
    code_list = code_df.values.tolist()

    stock_codes = [x[0] for x in code_list]

    # 登录系统
    lg = bs.login()
    logger.info(f"登录状态: {lg.error_code} - {lg.error_msg}")
    for stock_code in stock_codes:
        logger.info(f"正在处理：{stock_code}")
        df = get_multiple_stocks(stock_code, start_date, end_date)
        if df is None:
            logger.error(f"stock_update>>>>>>代码：{stock_code}无值")
        else:
            with engine.begin() as conn:
                df.to_sql(name=table_name, con=conn, if_exists='append')
                logger.info(f"表名：{table_name}、数量：{df.shape[0]}")
    # 登出系统
    bs.logout()


def all_stock_update(start_date: str, end_date: str) -> None:
    """
    更新所有股票数据

    Args:
        start_date: 开始日期
        end_date: 结束日期
    """
    table_name = f'data_gpsj_day_all' + start_date.replace("-", "")

    sql = string_enum.AG_STOCK_SQL3
    code_df = pd.read_sql(sql, con=con)
    code_list = code_df.values.tolist()

    stock_codes = [x[0] for x in code_list]

    # 登录系统
    lg = bs.login()
    logger.info(f"登录状态: {lg.error_code} - {lg.error_msg}")
    for stock_code in stock_codes:
        logger.info(f"正在处理：{stock_code}")
        df = get_multiple_stocks(stock_code, start_date, end_date)
        logger.info(f"{df.shape[0]}")
        if df is None:
            logger.error(f"stock_update>>>>>>代码：{stock_code}无值")
        else:
            with engine.begin() as conn:
                df.to_sql(name=table_name, con=conn, if_exists='append')
                logger.info(f"表名：{table_name}、数量：{df.shape[0]}")
    # 登出系统
    bs.logout()


def get_baostock_collection(start_date: str, end_date: str) -> None:
    """
    采集Baostock数据

    Args:
        start_date: 开始日期
        end_date: 结束日期
    """
    base_query_day_sql = f"select trade_date from data_jyrl where trade_date between '{start_date}' and '{end_date}' and trade_status='1' order by trade_date desc "
    base_query_day_df = pd.read_sql(base_query_day_sql, con=con)
    base_query_days = base_query_day_df.values.tolist()
    for day in base_query_days:
        set_date = day[0]
        stock_update(set_date, set_date)


if __name__ == "__main__":
    start = time.time()

    start_time = config_util.get_config('exe.history.baostock_collection.start_time')
    end_time = config_util.get_config('exe.history.baostock_collection.end_time')

    get_baostock_collection(start_time, end_time)

    con.close()
    end = time.time()
    execution_time = end - start
    logger.info(f"代码执行时间为: {execution_time} 秒")
