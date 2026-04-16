"""
概念相关——同花顺 东方财富，百度
"""


import time
from pathlib import Path

import adata
import pandas as pd
from sqlalchemy import create_engine

from gs2026.utils import mysql_util, config_util, log_util,string_enum
from gs2026.utils.pandas_display_config import set_pandas_display_options

logger = log_util.setup_logger(str(Path(__file__).absolute()))
set_pandas_display_options()

url = config_util.get_config("common.url")

engine = create_engine(url,pool_recycle=3600,pool_pre_ping=True)
con = engine.connect()
mysql_tool = mysql_util.get_mysql_tool(url)


def gnzsxx_east():
    """
    东方财富 概念指数信息
    :return: 
    """
    table_name1 = "data_east_gnzsxx"
    df = adata.stock.info.all_concept_code_east()
    print(df)
    with engine.begin() as conn:
        df.to_sql(name=table_name1, con=conn, if_exists='replace')


def gnzscfxx_east():
    """
    东方财富 概念指数成分信息
    :return: 
    """
    table_name1 = "data_east_gnzsxx"
    table_name2 = 'data_east_gnzscfxx'
    mysql_tool.drop_mysql_table(table_name2)
    sql = f"select index_code from {table_name1} where index_code is not null"
    lists = pd.read_sql(sql, con=con).values.tolist()
    print(lists)
    for i in lists:
        dm = i[0]
        print(dm)
        if i[0] is not None:
            try:
                df = adata.stock.info.concept_constituent_east(concept_code=dm)
                df['index_code'] = dm
                print(df)
                if df.empty:
                    logger.error("gnzscfxx_east》》》" + dm + "》》》未获取值")
                else:
                    with engine.begin() as conn:
                        df.to_sql(name=table_name2, con=conn, if_exists='append')
            except AttributeError:
                logger.error("gnzscfxx_east》》》"+dm+"》》》未获取值")
        else:
            logger.error("gnzscfxx_east》》》"+dm+"》》》未获取值")



def dzgpssgn_east():
    """
    东方财富 单只股票所属概念
    :return: 
    """
    table_name3 = 'data_east_dzgpssgn'
    mysql_tool.drop_mysql_table(table_name3)
    sql = string_enum.AG_STOCK_SQL1
    lists = pd.read_sql(sql, con=con).values.tolist()
    print(lists)
    for i in lists:
        dm = i[0]
        print(dm)
        if i[0] is not None:
            try:
                df = adata.stock.info.get_concept_east(stock_code=dm)
                print(df)
                if df.empty:
                    logger.error("dzgpssgn_east》》》" + dm + "》》》未获取值")
                else:
                    with engine.begin() as conn:
                        df.to_sql(name=table_name3, con=conn, if_exists='append')
            except AttributeError:
                logger.error("dzgpssgn_east》》》"+dm+"》》》未获取值")
        else:
            logger.error("dzgpssgn_east》》》"+dm+"》》》未获取值")


def dzgpssbk_east():
    """
    东方财富 单只股票所属板块
    :return: 
    """
    table_name3 = 'data_east_dzgpssgn'
    mysql_tool.drop_mysql_table(table_name3)
    sql = string_enum.AG_STOCK_SQL1
    lists = pd.read_sql(sql, con=con).values.tolist()
    print(lists)
    for i in lists:
        dm = i[0]
        print(dm)
        if i[0] is not None:
            try:
                df = adata.stock.info.get_plate_east(stock_code=dm)
                print(df)
                if df.empty:
                    logger.error("dzgpssbk_east》》》" + dm + "》》》未获取值")
                else:
                    with engine.begin() as conn:
                        df.to_sql(name=table_name3, con=conn, if_exists='append')
            except AttributeError:
                logger.error("dzgpssbk_east》》》"+dm+"》》》未获取值")
        else:
            logger.error("dzgpssbk_east》》》"+dm+"》》》未获取值")


def gnzsxx_ths():
    """
    同花顺 概念指数信息
    :return: 
    """
    gnzsxx_ths_table_name = "data_ths_gnzsxx"
    mysql_tool.drop_mysql_table(gnzsxx_ths_table_name)
    agdm_df = adata.stock.info.all_concept_code_ths()
    agdm_df = agdm_df[~agdm_df['index_code'].isna()]
    print(agdm_df)
    if agdm_df.empty:
        logger.error("data_ths_gnzsxx》》》》》》未获取值")
    else:
        with engine.begin() as conn:
            agdm_df.to_sql(name=gnzsxx_ths_table_name, con=conn, if_exists='replace')


def gnzscfxx_ths():
    """
    同花顺 概念指数成分信息
    :return: 
    """
    table_name1 = "data_ths_gnzsxx"
    table_name2 = 'data_ths_gnzscfxx'
    mysql_tool.drop_mysql_table(table_name2)
    sql = f"select index_code from {table_name1} where index_code is not null"
    lists = pd.read_sql(sql, con=con).values.tolist()
    print(lists)
    for i in lists:
        dm = i[0]
        print(dm)
        if i[0] is not None:
            try:
                df = adata.stock.info.concept_constituent_ths(index_code=dm)
                df['index_code'] = dm
                print(df)
                if df.empty:
                    logger.error("gnzscfxx_ths》》》" + dm + "》》》未获取值")
                else:
                    with engine.begin() as conn:
                        df.to_sql(name=table_name2, con=conn, if_exists='append')
            except AttributeError:
                logger.error("gnzscfxx_ths》》》"+dm+"》》》未获取值")
        else:
            logger.error("gnzscfxx_ths》》》"+dm+"》》》未获取值")


def dzgpssgn_ths():
    """
    同花顺 单只股票所属概念
    :return: 
    """
    table_name3 = 'data_ths_dzgpssgn'
    mysql_tool.drop_mysql_table(table_name3) # 603067
    sql = string_enum.AG_STOCK_SQL1
    dzgpssgn_ths_list = pd.read_sql(sql, con=con).values.tolist()
    print(dzgpssgn_ths_list)
    for i in dzgpssgn_ths_list:
        dm = i[0]
        print(dm)
        if i[0] is not None:
            try:
                df = adata.stock.info.get_concept_ths(stock_code=dm)
                print(df)
                if df.empty:
                    logger.error("dzgpssgn_ths》》》" + dm + "》》》未获取值")
                else:
                    with engine.begin() as conn:
                        df.to_sql(name=table_name3, con=conn, if_exists='append')
            except AttributeError:
                logger.error("dzgpssgn_ths》》》"+dm+"》》》未获取值")
        else:
            logger.error("dzgpssgn_ths》》》"+dm+"》》》未获取值")



def dzgpssgn_baidu():
    """
    百度 单只股票所属概念
    :return: 
    """
    table_name3 = 'data_baidu_dzgpssgn'
    str1 = ''
    if str1=='':
        print("全部输出")
        mysql_tool.drop_mysql_table(table_name3)
    else:
        print("增量输出")
    sql = string_enum.AG_STOCK_SQL1 + str1
    lists = pd.read_sql(sql, con=con).values.tolist()
    print(lists)
    for i in lists:
        dm = i[0]
        print(dm)
        if i[0] is not None:
            try:
                df = adata.stock.info.get_concept_baidu(stock_code=dm)
                print(df)
                if df.empty:
                    logger.error("dzgpssgn_baidu》》》" + dm + "》》》未获取值")
                else:
                    df.to_sql(name=table_name3, con=con, if_exists='append')
            except AttributeError:
                logger.error("dzgpssgn_baidu》》》"+dm+"》》》未获取值")
        else:
            logger.error("dzgpssgn_baidu》》》"+dm+"》》》未获取值")



if __name__ == '__main__':
    start = time.time()
    # print("========================东方财富概念数据=============================")
    # gnzsxx_east()
    # gnzscfxx_east()
    # dzgpssgn_east()
    # dzgpssbk_east()
    # print("========================同花顺概念数据=============================")
    # gnzsxx_ths()
    # gnzscfxx_ths()
    # dzgpssgn_ths()
    print("========================百度概念数据=============================")
    dzgpssgn_baidu()

    con.close()
    end = time.time()
    execution_time = end - start
    print(f"代码执行时间为: {execution_time} 秒")
