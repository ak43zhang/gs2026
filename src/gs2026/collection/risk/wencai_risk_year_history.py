"""
问财获取风险数据
    维度：年
"""
import time
import warnings
from pathlib import Path

import pandas as pd
from playwright.sync_api import TimeoutError, TimeoutError as PlaywrightTimeoutError
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
mysql_tool = mysql_util.get_mysql_tool(url)

def wencai_risk_year_get(year: str):
    last_year = str(int(year)-1)
    last_2year = str(int(year)-2)
    last_3year = str(int(year)-3)
 
    base_query = f'主板，非st，{year}总市值20亿到200亿，{year}实际流通市值10亿到150亿，{year}上市交易天数>180天,{year}股价大于3元,'
    table_name = 'wencaiquery_venture_year'

    # 风险标志：
    #   年报被出具“无法表示意见”或“否定意见”的审计报告。
    #   存在重大会计差错更正或财务造假（追溯调整后触发退市条件）。
    # 风险阈值：
    #   控股股东非经营性占用资金超净资产30 % 或金额超2亿元。·
    #   违规担保未解除且金额超净资产10 %。
    # ['净资产为负', '净资产为负'],
    query_lists = [
        ['机构持股', f'{last_year}年机构持股占流通股比例>60%,{last_year}年机构持股家数>10家'],
        # ['客户集中度', f'{last_year}年前五大客户销售额占比大于60%'],
        ['连续两年净利润为负',f'{last_2year}年{last_year}年连续两年净利润为负'],
        ['年报预告净利润小于负3亿',f'{last_year}年报预告净利润小于负3亿，{last_year}业绩预告类型不是减亏'],
        ['营收低于3亿元', f'{last_year}年营收低于3亿元'],
        ['连续营收减少1', f'{last_year}年总收入为空,{last_3year}年总收入>{last_2year}年总收入*1.5'],
        ['连续营收减少2', f'{last_3year}年总收入>{last_2year}年总收入>{last_year}年总收入'],
        ['资产负债率大于百分之90_1', f'{last_year}年资产负债率为空,{last_2year}年资产负债率>90%,{last_3year}年资产负债率>90%'],
        ['资产负债率大于百分之90_2', f'{last_year}年资产负债率>90%,{last_2year}年资产负债率>90%'],
        ['连续三年未分红', f'{last_year}年未分红,{last_2year}年未分红,{last_3year}年未分红'],
        ['近两年股价最低值小于2元',f'{last_year}年到{year}年最低价小于2元']
    ]

    for query_list in query_lists:
        query = base_query + query_list[1]
        logger.info(query)
        fxlx = query_list[0]
        save_mysql(query, fxlx, year, table_name)

@db_retry(max_retries=5,initial_delay=1,max_delay=60,retriable_errors=(OperationalError, TimeoutError,AttributeError,PlaywrightTimeoutError))
def save_mysql(query:str,fxlx:str,year:str,table_name:str):
    try:
        df = wencai_collection.wencai_query_base(query,fxlx)
        unique_df = df.drop_duplicates()
        unique_df['year'] = year
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
            mysql_tool.delete_data(f"DELETE FROM `{table_name}` WHERE `风险类型`='{fxlx}' and `year`='{year}'")
        with engine.begin() as conn:
            unique_df.to_sql(name=table_name, con=conn, if_exists='append', index=False)
            print("表名：" + table_name + "、数量：" + str(unique_df.shape[0]))

# 问财风险数据
def wencai_risk_year_collect(start_date, end_date):
    # 多年
    deal_day_sql = f"select DISTINCT YEAR(trade_date) from data_jyrl where  trade_date between '{start_date}' and '{end_date}' and trade_status='1' ORDER BY YEAR(trade_date) DESC "
    deal_day_df = pd.read_sql(deal_day_sql, con=con)
    days = deal_day_df.values.tolist()
    # print(days)
    for day in days:
        deal_set_date = str(day[0])
        print("-------------------------------------------------------" + deal_set_date)
        wencai_risk_year_get(deal_set_date)

if __name__ == "__main__":
    start = time.time()

    start_time = config_util.get_config("exe.history.wencai_risk_year_history.start_time")
    end_time = config_util.get_config("exe.history.wencai_risk_year_history.end_time")

    wencai_risk_year_collect(start_time, end_time)

    con.close()

    end = time.time()
    execution_time = end - start
    print(f"代码执行时间为: {execution_time} 秒")