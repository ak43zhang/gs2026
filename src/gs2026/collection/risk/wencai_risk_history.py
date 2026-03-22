"""
问财获取风险数据
    维度：每日
"""

import time
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd
from playwright.sync_api import Error
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError, SAWarning

from gs2026.collection.base import wencai_collection
from gs2026.utils import mysql_util, config_util, log_util
from gs2026.utils.decorators_util import db_retry
from gs2026.utils.pandas_display_config import set_pandas_display_options

warnings.filterwarnings("ignore", category=SAWarning)

logger = log_util.setup_logger(str(Path(__file__).absolute()))
set_pandas_display_options()

url = config_util.get_config("common.url")
engine = create_engine(url,pool_recycle=3600,pool_pre_ping=True)
con = engine.connect()
mysql_tool = mysql_util.MysqlTool(url)


def wencai_risk_get(now_str: str):
    date_sql = f"select trade_date from  ((select trade_date from data_jyrl where trade_status=1 and trade_date<='{now_str}' order by trade_date desc limit 250) union (select trade_date from data_jyrl where trade_status=1 and trade_date>'{now_str}' order by trade_date  limit 15)) as ta1 order by trade_date desc limit 300"
    day_df = pd.read_sql(date_sql, con=con)

    zt = day_df['trade_date'][16]
    ten_days_ago = day_df['trade_date'][26]
    one_months_ago = day_df['trade_date'][36]
    one_year_ago = day_df['trade_date'][257]
    ten_days_after = day_df['trade_date'][6]
    year = datetime.strptime(now_str, '%Y-%m-%d').year

    table_name = f'wencaiquery_venture_{year}'

    # 风险标志：
    #   年报被出具“无法表示意见”或“否定意见”的审计报告。
    #   存在重大会计差错更正或财务造假（追溯调整后触发退市条件）。
    # 风险阈值：
    #   控股股东非经营性占用资金超净资产30 % 或金额超2亿元。
    #   违规担保未解除且金额超净资产10 %。
    query_lists = [
        ['立案调查', f'{one_year_ago}到{zt}被立案调查的股'],
        ['分红派息', f'{zt}到{ten_days_after}有分红'],
        ['监管日期', f'监管日期是{one_months_ago}到{zt}'],
        ['流动性风险_换手', f'{ten_days_ago}到{zt}连续换手都小于1%'],
        ['流动性风险_换手2', f'{one_months_ago}到{zt}区间换手率小于20%'],
        ['融资余额风险',f'{zt}融资余额/流通市值>10%'],
        ['解禁', f'{ten_days_ago}到{ten_days_after}解禁']
    ]

    for querylist in query_lists:
        query = f'主板，非st，{zt}总市值20亿到200亿，{zt}实际流通市值10亿到150亿，{zt}上市交易天数>180天,{zt}股价大于3元,'
        query = query + querylist[1]
        logger.info(query)
        fxlx = querylist[0]
        save_mysql(query, fxlx, now_str, table_name)



# 应用重试机制到原函数
@db_retry(max_retries=5,initial_delay=1,max_delay=60,retriable_errors=(OperationalError, TimeoutError,AttributeError,Error))
def save_mysql(query:str,fxlx:str,now_str:str,table_name:str):
    try:
        df = wencai_collection.wencai_query_base(query,fxlx)
        unique_df = df.drop_duplicates().copy()
        unique_df['trade_date'] = now_str
    except TimeoutError:
        logger.error("表格未显示，风险类型：" + fxlx)
        raise
    except Exception:
        # 捕获其他异常类型
        raise

    if unique_df.empty:
        logger.error("wencaiquery》》》" + fxlx + "》》》未获取值")
    else:
        # 判断表是否存在，存在则删除数据再重新写入，不存在则直接写入
        if mysql_tool.check_table_exists(table_name):
            mysql_tool.delete_data(
                f"DELETE FROM `{table_name}` WHERE `风险类型`='{fxlx}' and `trade_date`='{now_str}'")
        with engine.begin() as conn:
            unique_df.to_sql(name=table_name, con=conn, if_exists='append', index=False)
            print("表名：" + table_name + "、数量：" + str(unique_df.shape[0]))

# 问财风险数据
def wencai_risk_collect(start_date:str, end_date:str):
    # 多天
    deal_day_sql = f"select trade_date from data_jyrl where  trade_date between '{start_date}' and '{end_date}' and trade_status='1' order by trade_date desc "
    deal_day_df = pd.read_sql(deal_day_sql, con=con)
    days = deal_day_df.values.tolist()
    for day in days:
        deal_set_date = day[0]
        print("-------------------------------------------------------" + deal_set_date)
        wencai_risk_get(deal_set_date)


if __name__ == "__main__":
    start = time.time()

    start_time = config_util.get_config("exe.history.wencai_risk_history.start_time")

    end_time = config_util.get_config("exe.history.wencai_risk_history.end_time")

    wencai_risk_collect(start_time, end_time)

    con.close()

    end = time.time()
    execution_time = end - start
    print(f"代码执行时间为: {execution_time} 秒")