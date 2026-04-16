"""
可转债数据获取
"""
import time
import warnings
from pathlib import Path

import akshare as ak
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning

from gs2026.utils import mysql_util, config_util,log_util
from gs2026.utils.pandas_display_config import set_pandas_display_options

warnings.filterwarnings("ignore", category=SAWarning)

logger = log_util.setup_logger(str(Path(__file__).absolute()))
set_pandas_display_options()

url = config_util.get_config("common.url")

engine = create_engine(url,pool_recycle=3600,pool_pre_ping=True)
con = engine.connect()
mysql_tool = mysql_util.get_mysql_tool(url)


def get_bond():
    table_name = 'data_bond'
    table_name2 = 'data_bond_qs_jsl'
    table_name3 = 'data_bond_ths'
    mysql_tool.drop_mysql_table(table_name)
    mysql_tool.drop_mysql_table(table_name2)
    mysql_tool.drop_mysql_table(table_name3)
    try:
        df = ak.bond_zh_cov()
        # print(df)
        if df.empty:
            logger.error("可转债未获取值")
        else:
            with engine.begin() as conn:
                df.to_sql(name=table_name, con=conn, if_exists='replace')
                print("表名：" + table_name + "、数量：" + str(df.shape[0]))

        df2 = ak.bond_cb_redeem_jsl()
        # print(df2)
        if df2.empty:
            logger.error("可转债强赎未获取值")
        else:
            with engine.begin() as conn:
                df2.to_sql(name=table_name2, con=conn, if_exists='replace')
                print("表名：" + table_name2 + "、数量：" + str(df2.shape[0]))

        df3 = ak.bond_zh_cov_info_ths()
        # print(df3)
        if df3.empty:
            logger.error("可转债——同花顺版未获取值")
        else:
            with engine.begin() as conn:
                df3.to_sql(name=table_name3, con=conn, if_exists='replace')
                print("表名：" + table_name3 + "、数量：" + str(df3.shape[0]))
            conn.commit()
            conn.close()
    except AttributeError:
        logger.error("可转债表未获取值")


def get_bond_daily():
    table_name = "data_bond_daily"
    mysql_tool.drop_mysql_table(table_name)
    sql = """
    SELECT 
    `代码`,`正股代码`,
    CONCAT(
        CASE 
            WHEN `正股代码` LIKE '00%' OR `正股代码` LIKE '30%'  THEN 'sz'
            WHEN `正股代码` LIKE '60%' OR `正股代码` LIKE '68%' THEN 'sh'
            ELSE 'other'
            END,
            `代码`
        ) AS `债券代码`
        FROM data_bond_qs_jsl  where `正股代码` like '00%' or `正股代码` LIKE '60%' or `正股代码` LIKE '30%' OR `正股代码` LIKE '68%'
    """.replace("%","%%")
    dm_df = pd.read_sql(sql, con=con)
    datas = dm_df.values.tolist()
    for data in datas:
        bond_code = data[0]
        stock_code = data[1]
        bond_code_2 = data[2]
        print(bond_code,stock_code,bond_code_2)
        try:
            bond_df = ak.bond_zh_hs_cov_daily(bond_code_2)
            bond_df['stock_code'] = stock_code
            bond_df['bond_code'] = bond_code
            bond_df['bond_code_2'] = bond_code_2
            # print(bond_df)
            if bond_df.empty:
                logger.error("data_bond_daily>>>>>>" + bond_code + ">>>>>>未获取值")
            else:
                with engine.begin() as conn:
                    bond_df.to_sql(name=table_name, con=conn, if_exists='append')
                    print("表名：" + table_name + "、数量：" + str(bond_df.shape[0]))
                conn.commit()
                conn.close()
        except KeyError:
            logger.error("data_bond_daily>>>>>>" + bond_code + ">>>>>>未获取值")



if __name__ == "__main__":
    start = time.time()

    # get_bond()
    # get_bond_daily()

    # bond_zh_hs_cov_daily_df = ak.bond_zh_hs_cov_daily(symbol="sz127112")
    # print(bond_zh_hs_cov_daily_df)

    # 实时数据
    # bond_zh_hs_cov_spot_df = ak.bond_zh_hs_cov_spot()
    # print(bond_zh_hs_cov_spot_df)

    my_jsl_cookie = 'kbzw__Session=3h11lqdnn7fbmemkglivvp7fd1; Hm_lvt_164fe01b1433a19b507595a43bf58262=1772508021; HMACCOUNT=8407E7F96719D8FA; kbz_newcookie=1; kbzw__user_login=7Obd08_P1ebax9aXwZWrlqqvp6-TooKvpuXK7N_u0ejF1dSe3Jqgxabep8-sodvHq5iw29eskdXEqN7boauk2Jfala-YrqXW2cXS1qCbq6OtmKeRmLKgubXOvp-qrKCroaeaqJesmK6ltrG_0aTC2PPV487XkKylo5iJx8ri3eTg7IzFtpaSp6Wjs4HHyuKvqaSZ5K2Wn4G45-PkxsfG1sTe3aihqpmklK2Xm8OpxK7ApZXV4tfcgr3G2uLioYGzyebo4s6onauXpJGlp6GogcPC2trn0qihqpmklK2XuNzIn5KorqOZp5ylkg..; Hm_lpvt_164fe01b1433a19b507595a43bf58262=1772508695; SERVERID=0e73f01634e37a9af0b56dfcd9143ef3|1772508875|1772508021'
    bond_cb_jsl_df = ak.bond_cb_jsl(cookie=my_jsl_cookie)
    print(bond_cb_jsl_df)

    con.close()
    end = time.time()
    execution_time = end - start
    logger.info(f"代码执行时间为: {execution_time} 秒")