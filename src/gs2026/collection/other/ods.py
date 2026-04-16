"""
预约披露时间_东方财富  数据采集
"""
import time
from pathlib import Path

import akshare as ak
import pandas as pd
from sqlalchemy import create_engine

from gs2026.utils import mysql_util, config_util, log_util
from gs2026.utils.config_util import get_config
from gs2026.utils.pandas_display_config import set_pandas_display_options

logger = log_util.setup_logger(str(Path(__file__).absolute()))
set_pandas_display_options()

config = get_config
url = config_util.get_config("common.url")

engine = create_engine(url,pool_recycle=3600,pool_pre_ping=True)
con = engine.connect()
mysql_tool = mysql_util.get_mysql_tool(url)


def yyplsj_east(east_start_time: str, east_end_time: str):
    yyplsj_east_table = "ods_yyplsj_east"
    day_sql = f"select trade_date from data_jyrl where  trade_date between '{east_start_time}' and '{east_end_time}' order by trade_date desc"
    day_df = pd.read_sql(day_sql, con=con)
    print(day_df)
    sj_list = day_df.values.tolist()
    for day in sj_list:
        sj = day[0].replace("-", "")
        try:
            df = ak.stock_yysj_em(symbol="沪深A股", date=sj)
            with engine.begin() as conn:
                df.to_sql(yyplsj_east_table, con=conn, if_exists='append', index=False)
        except Exception as e:
            logger.error(f"{sj}无数据")



if __name__ == "__main__":
    start = time.time()

    # 将当前日期格式化为 yyyy-MM-dd 字符串
    start_time = config_util.get_config("exe.history", "")['collection_other_ods']['start_time']
    end_time = config_util.get_config("exe.history", "")['collection_other_ods']['end_time']

    print("=======================预约披露时间_东方财富  数据采集================================")
    yyplsj_east(start_time,end_time)

    con.close()

    end = time.time()
    execution_time = end - start
    print(f"代码执行时间为: {execution_time} 秒")