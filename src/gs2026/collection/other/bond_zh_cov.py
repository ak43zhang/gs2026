"""
可转债数据获取
"""
import time
import warnings
from pathlib import Path

import akshare as ak
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SAWarning

from gs2026.utils import mysql_util, config_util, log_util
from gs2026.utils.pandas_display_config import set_pandas_display_options

warnings.filterwarnings("ignore", category=SAWarning)

logger = log_util.setup_logger(str(Path(__file__).absolute()))
set_pandas_display_options()

url = config_util.get_config("common.url")

# 创建引擎但不立即建立连接
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
mysql_tool = mysql_util.get_mysql_tool(url)


def get_bond():
    """采集可转债基础信息
    
    修复：不在模块级别保持连接，每次使用时新建连接，
    避免长连接持有元数据锁阻塞DROP TABLE
    """
    table_name = 'data_bond'
    table_name2 = 'data_bond_qs_jsl'
    table_name3 = 'data_bond_ths'
    
    # 删除旧表
    mysql_tool.drop_mysql_table(table_name)
    mysql_tool.drop_mysql_table(table_name2)
    mysql_tool.drop_mysql_table(table_name3)
    
    try:
        # 采集可转债基础信息
        df = ak.bond_zh_cov()
        if df.empty:
            logger.error("可转债未获取值")
        else:
            with engine.begin() as conn:
                df.to_sql(name=table_name, con=conn, if_exists='replace')
                print("表名：" + table_name + "、数量：" + str(df.shape[0]))

        # 采集可转债强赎信息
        df2 = ak.bond_cb_redeem_jsl()
        if df2.empty:
            logger.error("可转债强赎未获取值")
        else:
            with engine.begin() as conn:
                df2.to_sql(name=table_name2, con=conn, if_exists='replace')
                print("表名：" + table_name2 + "、数量：" + str(df2.shape[0]))

        # 采集可转债同花顺信息
        df3 = ak.bond_zh_cov_info_ths()
        if df3.empty:
            logger.error("可转债——同花顺版未获取值")
        else:
            with engine.begin() as conn:
                df3.to_sql(name=table_name3, con=conn, if_exists='replace')
                print("表名：" + table_name3 + "、数量：" + str(df3.shape[0]))
                
    except AttributeError as e:
        logger.error(f"可转债表未获取值: {e}")


def get_bond_daily():
    """采集可转债日线数据
    
    修复：使用新的连接查询data_bond_qs_jsl，避免使用模块级别的长连接
    """
    table_name = "data_bond_daily"
    mysql_tool.drop_mysql_table(table_name)
    
    # 使用新连接查询债券代码列表
    sql = """
    SELECT 
    `代码`,`正股代码`,
    CONCAT(
        CASE 
            WHEN `正股代码` LIKE '00%%' OR `正股代码` LIKE '30%%'  THEN 'sz'
            WHEN `正股代码` LIKE '60%%' OR `正股代码` LIKE '68%%' THEN 'sh'
            ELSE 'other'
            END,
            `代码`
        ) AS `债券代码`
        FROM data_bond_qs_jsl  where `正股代码` like '00%%' or `正股代码` LIKE '60%%' or `正股代码` LIKE '30%%' OR `正股代码` LIKE '68%%'
    """
    
    with engine.connect() as conn:
        dm_df = pd.read_sql(text(sql), con=conn)
    
    datas = dm_df.values.tolist()
    for data in datas:
        bond_code = data[0]
        stock_code = data[1]
        bond_code_2 = data[2]
        print(bond_code, stock_code, bond_code_2)
        try:
            bond_df = ak.bond_zh_hs_cov_daily(bond_code_2)
            bond_df['stock_code'] = stock_code
            bond_df['bond_code'] = bond_code
            bond_df['bond_code_2'] = bond_code_2
            if bond_df.empty:
                logger.error("data_bond_daily>>>>>>" + bond_code + ">>>>>>未获取值")
            else:
                with engine.begin() as conn:
                    bond_df.to_sql(name=table_name, con=conn, if_exists='append')
                    print("表名：" + table_name + "、数量：" + str(bond_df.shape[0]))
        except KeyError:
            logger.error("data_bond_daily>>>>>>" + bond_code + ">>>>>>未获取值")


if __name__ == "__main__":
    start = time.time()

    get_bond()
    get_bond_daily()

    end = time.time()
    execution_time = end - start
    logger.info(f"代码执行时间为: {execution_time} 秒")