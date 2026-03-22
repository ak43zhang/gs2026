"""
akshare采集相关数据
    同花顺概念指数信息
    同花顺概念指数成分信息
    同花顺单只股票所属概念
"""

import time

import adata
import pandas as pd
from bs4 import NavigableString
from loguru import logger
from sqlalchemy import create_engine

from gs2026.utils import mysql_util, config_util

# 数据库连接配置
url = config_util.get_config('common.url')
engine = create_engine(url,pool_recycle=3600,pool_pre_ping=True)
con = engine.connect()
mysql_util = mysql_util.MysqlTool(url)


def clean_dataframe_for_sql(df):
    """
    清理DataFrame中的特殊对象类型，使其适合写入SQL数据库 空值写为字符串nan
    """
    df_clean = df.copy()

    for col in df_clean.columns:
        # 检查列中是否包含NavigableString或其他特殊对象
        if df_clean[col].dtype == 'object':
            # 将列转换为字符串，处理特殊对象
            df_clean[col] = df_clean[col].apply(
                lambda x: str(x) if isinstance(x, NavigableString) else x
            )
            # 最后确保都是字符串
            df_clean[col] = df_clean[col].astype(str)

    return df_clean

#同花顺概念指数信息
def gnzsxx_ths():
    table_name1 = "data_gnzsxx_ths"
    mysql_util.drop_mysql_table(table_name1)
    df = adata.stock.info.all_concept_code_ths()
    df_clean = clean_dataframe_for_sql(df)
    print(df_clean)
    df_clean.to_sql(name=table_name1, con=con, if_exists='replace')

# 概念指数成分信息
def gnzscfxx_ths():
    table_name1 = "data_gnzsxx_ths"
    table_name2 = 'data_gnzscfxx_ths'
    mysql_util.drop_mysql_table(table_name2)
    sql = f"select index_code from {table_name1} where index_code is not null or index_code !='nan'"
    lists = pd.read_sql(sql, con=con).values.tolist()
    print(lists)
    for i in lists:
        dm = i[0]
        print(dm)
        if dm is not None:
            try:
                df = adata.stock.info.concept_constituent_ths(index_code=dm)
                df['index_code'] = dm
                print(df)
                if df is None or df.empty:
                    logger.error("gnzscfxx_ths》》》" + str(dm) + "》》》未获取值")
                else:
                    with engine.begin() as conn:  # 自动事务管理
                        df.to_sql(name=table_name2, con=conn, if_exists='append')
            except AttributeError as err:
                logger.error("gnzscfxx_ths》》》"+str(dm)+"》》》未获取值")
        else:
            logger.error("gnzscfxx_ths》》》"+str(dm)+"》》》未获取值")


## 单只股票所属概念
# and stock_code not in (select distinct stock_code from data2024_dzgpssgn_ths)
def dzgpssgn_ths():
    table_name3 = 'data_dzgpssgn_ths'
    mysql_util.drop_mysql_table(table_name3)
    sql = "select stock_code from data_agdm where (stock_code like '00%' or stock_code like '60%' or stock_code like '30%')"
    lists = pd.read_sql(sql, con=con).values.tolist()
    print(lists)
    for i in lists:
        dm = i[0]
        print(dm)
        if dm is not None:
            try:
                df = adata.stock.info.get_concept_ths(stock_code=dm)
                print(df)
                if df is None or df.empty:
                    logger.error("dzgpssgn_ths》》》" + dm + "》》》未获取值")
                else:
                    with engine.begin() as conn:  # 自动事务管理
                        df.to_sql(name=table_name3, con=conn, if_exists='append')
            except AttributeError as err:
                logger.error("dzgpssgn_ths》》》"+str(dm)+"》》》未获取值")
        else:
            logger.error("dzgpssgn_ths》》》"+str(dm)+"》》》未获取值")

if __name__ == "__main__":
    start = time.time()

    try:
        gnzsxx_ths()
        gnzscfxx_ths()
        dzgpssgn_ths()
    finally:
        con.commit()
        con.close()


    end = time.time()
    execution_time = end - start
    print(f"代码执行时间为: {execution_time} 秒")
