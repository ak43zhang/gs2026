"""
板块、概念指数日级别数据采集
用于分析市场情绪与权重股和其他股的关系
"""
import time
import warnings

import akshare as ak
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning
from loguru import logger

from gs2026.utils import mysql_util, config_util
from gs2026.utils.pandas_display_config import set_pandas_display_options
from gs2026.constants import FIREFOX_1408

warnings.filterwarnings("ignore", category=SAWarning)

set_pandas_display_options()

url = config_util.get_config("common.url")
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()
browser_path = FIREFOX_1408
mysql_tool = mysql_util.get_mysql_tool(url)


def bulu(end_date):
    # 补录环节
    bl_sql = f"""
    (
    select a.`日期`,a.`name`,a.`code` from (select '{end_date}' as `日期`,name,code from ths_gn_names_rq  where  '{end_date}'>rq  and flag='1') as a 
        left join 
    (select * from ths_gn_bk where `日期`='{end_date}') as b 
    on a.name = b.name where b.name is null 
    )
    union all 
    (select `日期`,`name`,`code` from ths_gn_bk where `开盘价` is null)
    """
    # print(bl_sql)
    flag = True
    while flag:
        try:
            with engine.connect() as conn:
                lists = pd.read_sql(bl_sql, con=conn).values.tolist()
            if len(lists) != 0:
                for i in lists:
                    rq = str(i[0]).replace('-', '')
                    rq_ = i[0]
                    name = i[1]
                    code = i[2]
                    print(name, code)

                    df = ak.stock_board_concept_index_ths(symbol=name, start_date=rq, end_date=rq)
                    df['name'] = name
                    df['code'] = code

                    rows, columns = df.shape
                    print(f"----------------{name}共{rows}条指数数据--------------------")
                    print(df)

                    table_name = f'ths_gn_bk'

                    # 原子操作
                    if mysql_tool.check_table_exists(table_name):
                        mysql_tool.delete_data(
                            f"DELETE FROM `{table_name}` WHERE name = '{name}' and `日期` between '{rq_}' and '{rq_}'")
                    with engine.begin() as conn:
                        df.to_sql(table_name, con=conn, if_exists='append', index=False)
                    time.sleep(1)
            else:
                flag = False
        except KeyError as err:
            logger.error("》》》》》》未获取值")
        time.sleep(30)


def bk_gn_collect(start_date, end_date):
    # 获取同花顺的所有概念名称
    ths_gn_names = ak.stock_board_concept_name_ths()
    print(ths_gn_names)
    with engine.begin() as conn:
        ths_gn_names.to_sql('ths_gn_names', con=conn, if_exists='replace', index=True)

    base_query_day_sql = f"select trade_date from data_jyrl where  trade_date between '{start_date}' and '{end_date}' and trade_status='1' order by trade_date desc "
    base_query_day_df = pd.read_sql(base_query_day_sql, con=con)
    base_query_days = base_query_day_df.values.tolist()
    for day in base_query_days:
        set_date = day[0]
        print("当前时间" + set_date)
        bulu(set_date)


if __name__ == "__main__":
    start = time.time()

    start_time = config_util.get_config("exe.history.bk_gn_collection.start_time", "2026-04-03")
    end_time = config_util.get_config("exe.history.bk_gn_collection.end_time", "2026-04-15")

    bk_gn_collect(start_time, end_time)

    end = time.time()
    execution_time = end - start
    print(f"代码执行时间为: {execution_time} 秒")
