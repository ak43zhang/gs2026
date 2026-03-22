"""
指数宽基行情——zskj '000001','399401'
龙虎榜每日更新——today_lhb(date: str = None)
龙虎榜个股每日更新——history_lhb(start_time:str,end_time:str)
热度每日更新
    东方财富热股——hotstock_east
    同花顺热股——hotstock_ths
    同花顺热门板块——hotbk20_ths
融资融券每日更新——rzrq
股市日历——公式动态每日更新——gsdt
通达信风险数据——risk_tdx
同花顺 行业指数数据——industry_ths
行业指数成分数据——industry_code_component_ths
"""

import time
from typing import Optional

import adata
import akshare as ak
import pandas as pd
from loguru import logger
from sqlalchemy import create_engine

from gs2026.constants import SQL_STOCK_EXCLUDE_LARGE
from gs2026.utils import mysql_util, config_util
from gs2026.utils.pandas_display_config import set_pandas_display_options

set_pandas_display_options()

url = config_util.get_config("common.url")

engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()
mysql_tool = mysql_util.MysqlTool(url)


def zskj() -> None:
    """
    指数宽基行情
    :return:
    """
    table_name1 = "data_zsxx_ths"
    table_name2 = 'data_zshq_ths'
    mysql_tool.drop_mysql_table(table_name2)
    sql = f"select index_code from {table_name1} where index_code in ('000001','399401')"
    lists = pd.read_sql(sql, con=con).values.tolist()
    for i in lists:
        dm = i[0]
        if i[0] is not None:
            try:
                df = adata.stock.market.get_market_index(index_code=dm, start_date='1990-01-01')
                df['zstype'] = 'kj'
                if df.empty:
                    logger.error(f"data_zshq_ths>>>>>>{dm}>>>>>>未获取值")
                else:
                    with engine.begin() as conn:
                        df.to_sql(name=table_name2, con=conn, if_exists='append')
                        logger.info(f"表名：{table_name2}、数量：{df.shape[0]}")

                    conn.commit()
                    conn.close()
            except KeyError:
                logger.error(f"data_zshq_ths>>>>>>{dm}>>>>>>未获取值")
        else:
            logger.error(f"data_zshq_ths>>>>>>{dm}>>>>>>未获取值")


def today_lhb(start_time: str, end_time: str) -> None:
    """
    龙虎榜
    :param start_time: 开始时间
    :param end_time: 结束时间
    :return:
    """
    table_name = "data_lhb"
    sql = f"select trade_date from data_jyrl where trade_date between '{start_time}' and '{end_time}' and trade_status='1' order by trade_date desc "
    trade_date_df = pd.read_sql(sql, con=con)
    trade_date_list = trade_date_df.values.tolist()
    for td in trade_date_list:
        trade_date = td[0]
        df = adata.sentiment.hot.list_a_list_daily(report_date=trade_date)
        if df.empty:
            logger.error(f"龙虎榜>>>>>>{trade_date}>>>>>>无数据")
        else:
            if mysql_tool.check_table_exists(table_name):
                mysql_tool.delete_data(f"DELETE FROM `{table_name}` WHERE `trade_date`='{trade_date}' ")
            with engine.begin() as conn:
                df.to_sql(name=table_name, con=conn, if_exists='append')
                logger.info(f"表名：{table_name}、数量：{df.shape[0]}")


def history_lhb(start_time: str, end_time: str) -> None:
    """
    个股 历史龙虎榜数据获取
    :param start_time: 开始时间
    :param end_time: 结束时间
    :return:
    """
    table_name = 'data_lhb_history'
    if mysql_tool.check_table_exists(table_name):
        mysql_tool.delete_data(f"DELETE FROM `{table_name}` WHERE `trade_date` between '{start_time}' and '{end_time}' ")
    sql = f"select distinct stock_code,trade_date from data_lhb where trade_date between '{start_time}' and '{end_time}' order by trade_date desc"
    con_new = engine.connect()  # 更新龙虎榜数据但是如果用原来的链接数据未更新
    dm_kpsj_df = pd.read_sql(sql, con=con_new)
    dm_list = dm_kpsj_df.values.tolist()
    for dm_sj in dm_list:
        dm = dm_sj[0]
        sj = dm_sj[1]
        logger.info(f"代码：{dm} 时间：{sj}")
        df = adata.sentiment.hot.get_a_list_info(stock_code=dm, report_date=sj)
        if df.empty:
            logger.error(f"data_lhb_history>>>>>>代码：{dm} 时间：{sj}无值")
        else:
            with engine.begin() as conn:
                df.to_sql(name=table_name, con=conn, if_exists='append')
                logger.info(f"表名：{table_name}、数量：{df.shape[0]}")
            conn.commit()
            conn.close()


def hot_stock_east() -> None:
    """
    东方财富热股 rq：日期 cc：出处
    :return:
    """
    table_name = "hot_stock_east"
    df = adata.sentiment.hot.pop_rank_100_east()
    current_struct_time = time.localtime()
    formatted_time = time.strftime("%Y%m%d", current_struct_time)
    df['rq'] = formatted_time
    df['cc'] = 'east'
    if mysql_tool.check_table_exists(table_name):
        mysql_tool.delete_data(f"DELETE FROM `{table_name}` WHERE `rq`='{formatted_time}' ")
    with engine.begin() as conn:
        df.to_sql(name=table_name, con=conn, if_exists='append')
        logger.info(f"表名：{table_name}、数量：{df.shape[0]}")


def hot_stock_ths() -> None:
    """
    同花顺热股 rq：日期 cc：出处
    :return:
    """
    table_name = "hot_stock_ths"
    df = adata.sentiment.hot.hot_rank_100_ths()
    current_struct_time = time.localtime()
    formatted_time = time.strftime("%Y%m%d", current_struct_time)
    df['rq'] = formatted_time
    df['cc'] = 'ths'
    if mysql_tool.check_table_exists(table_name):
        mysql_tool.delete_data(f"DELETE FROM `{table_name}` WHERE `rq`='{formatted_time}' ")
    with engine.begin() as conn:
        df.to_sql(name=table_name, con=conn, if_exists='append')
        logger.info(f"表名：{table_name}、数量：{df.shape[0]}")


def hot_bk20_ths() -> None:
    """
    同花顺热门板块 rq：日期 cc：出处
    :return:
    """
    table_name = "hot_bk20_ths"
    df = adata.sentiment.hot.hot_concept_20_ths()
    current_struct_time = time.localtime()
    formatted_time = time.strftime("%Y%m%d", current_struct_time)
    df['rq'] = formatted_time
    df['cc'] = 'ths'
    if mysql_tool.check_table_exists(table_name):
        mysql_tool.delete_data(f"DELETE FROM `{table_name}` WHERE `rq`='{formatted_time}' ")
    with engine.begin() as conn:
        df.to_sql(name=table_name, con=conn, if_exists='append')
        logger.info(f"表名：{table_name}、数量：{df.shape[0]}")


def rzrq() -> None:
    """
    融资融券每日更新
    :return:
    """
    table_name = 'data_rzrq'
    mysql_tool.drop_mysql_table(table_name)
    try:
        df = adata.sentiment.securities_margin(start_date='2014-01-01')
        if df.empty:
            logger.error("rzrq未获取值")
        else:
            with engine.begin() as conn:
                df.to_sql(name=table_name, con=conn, if_exists='replace')
                logger.info(f"表名：{table_name}、数量：{df.shape[0]}")
            conn.commit()
            conn.close()
    except AttributeError:
        logger.error("rzrq未获取值")


def gsdt(start_time: str, end_time: str) -> None:
    """
    股市日历——股市动态每日更新
    :param start_time: 开始时间
    :param end_time: 结束时间
    :return:
    """
    table_name = "data_gsdt"
    sql = f"select trade_date from data_jyrl where trade_date between '{start_time}' and '{end_time}' and trade_status='1' order by trade_date desc "
    trade_date_df = pd.read_sql(sql, con=con)
    trade_date_list = trade_date_df.values.tolist()
    for i in trade_date_list:
        try:
            trade_date = i[0].replace("-", "")
            logger.info(f"---------------------------------------当前日期：{trade_date}")
            df = ak.stock_gsrl_gsdt_em(date=trade_date)
            if df.empty:
                logger.error(f"股市日历>>>>>>{trade_date}>>>>>>无数据")
            else:
                if mysql_tool.check_table_exists(table_name):
                    mysql_tool.delete_data(f"DELETE FROM `{table_name}` WHERE `交易日`='{trade_date}' ")
                with engine.begin() as conn:
                    df.to_sql(name=table_name, con=conn, if_exists='append')
                    logger.info(f"表名：{table_name}、数量：{df.shape[0]}")
            conn.commit()
            conn.close()
        except TypeError:
            logger.error("gsdt未获取值")


def code_update() -> None:
    """
    A股代码
    :return:
    """
    table_name = 'data_agdm'
    if mysql_tool.check_table_exists(table_name):
        mysql_tool.drop_mysql_table(table_name)
    df = adata.stock.info.all_code()
    with engine.begin() as conn:
        df.to_sql(name=table_name, con=conn, if_exists='replace')
        logger.info(f"表名：{table_name}、数量：{df.shape[0]}")
        conn.commit()
        conn.close()


def risk_tdx(start_time: str, end_time: str) -> None:
    """
    通达信风险数据获取
    :param start_time: 开始时间
    :param end_time: 结束时间
    :return:
    """
    table_name = 'data_risk_tdx'
    sql = f"select trade_date from data_jyrl where trade_date between '{start_time}' and '{end_time}' and trade_status='1' order by trade_date desc "
    trade_date_df = pd.read_sql(sql, con=con)
    trade_date_list = trade_date_df.values.tolist()
    for td in trade_date_list:
        try:
            trade_date = td[0]
            if mysql_tool.check_table_exists(table_name):
                mysql_tool.delete_data(f"DELETE FROM `{table_name}` WHERE `trade_date`='{trade_date}' ")
            sql = SQL_STOCK_EXCLUDE_LARGE.replace("%", "%%")
            code_df = pd.read_sql(sql, con=con)
            code_list = code_df.values.tolist()
            for code in code_list:
                dm = code[0]
                if code[1] is not None:
                    df = adata.sentiment.mine.mine_clearance_tdx(stock_code=dm)
                    df['trade_date'] = trade_date
                    if df.empty:
                        logger.error(f"risk_tdx>>>>>>{dm}>>>>>>未获取值")
                    else:
                        with engine.begin() as conn:
                            df.to_sql(name=table_name, con=conn, if_exists='append')
                            logger.info(f"表名：{table_name}、数量：{df.shape[0]}")
                else:
                    logger.error(f"risk_tdx>>>>>>代码：{dm}无值")
        except TypeError:
            logger.error("gsdt未获取值")


def industry_code_ths() -> None:
    """
    同花顺行业指数信息
    :return:
    """
    table_name = "data_industry_code_ths"
    mysql_tool.drop_mysql_table(table_name)
    df = ak.stock_board_industry_name_ths()
    if df.empty:
        logger.error("data_industry_code_ths》》》》》》未获取值")
    else:
        with engine.begin() as conn:
            df.to_sql(name=table_name, con=conn, if_exists='replace')
            logger.info(f"表名：{table_name}、数量：{df.shape[0]}")


def industry_code_component_ths() -> None:
    """
    同花顺 行业指数成分信息
    :return:
    """
    table_name = "data_industry_code_ths"
    table_name2 = "data_industry_code_component_ths"
    sql = f"select code,name from {table_name}"
    code_name_df = pd.read_sql(sql, con=con)
    code_name_list = code_name_df.values.tolist()
    for i in code_name_list:
        try:
            code = i[0]
            name = i[1]
            logger.info(f"---------------------------------------当前行业：{code} {name}")
            df = adata.stock.info.concept_constituent_ths(index_code=code)
            df['code'] = code
            df['name'] = name
            if df.empty:
                logger.error(f"行业>>>>>>{code} {name}>>>>>>无数据")
            else:
                if mysql_tool.check_table_exists(table_name2):
                    mysql_tool.delete_data(f"DELETE FROM `{table_name2}` WHERE `code`='{code}' ")
                with engine.begin() as conn:
                    df.to_sql(name=table_name2, con=conn, if_exists='append')
                    logger.info(f"表名：{table_name2}、数量：{df.shape[0]}")
            conn.commit()
            conn.close()
        except TypeError:
            logger.error("industry_code_component_ths未获取值")


def industry_ths() -> None:
    """
    同花顺 行业指数数据
    :return:
    """
    table_name = "data_industry_code_ths"
    table_name2 = "data_industry_ths"
    mysql_tool.drop_mysql_table(table_name2)
    sql = f"select code,name from {table_name}"
    lists = pd.read_sql(sql, con=con).values.tolist()
    for i in lists:
        code = i[0]
        name = i[1]
        if i[0] is not None:
            try:
                df = adata.stock.market.get_market_concept_ths(index_code=code)
                df['name'] = name
                if df.empty:
                    logger.error(f"data_industry_ths》》》{code}》》》未获取值")
                else:
                    with engine.begin() as conn:
                        df.to_sql(name=table_name2, con=conn, if_exists='append')
                        logger.info(f"表名：{table_name2}、数量：{df.shape[0]}")
            except AttributeError:
                logger.error(f"data_industry_ths》》》{code}》》》未获取值")
        else:
            logger.error(f"data_industry_ths》》》{code}》》》未获取值")


def get_base_collect(start_date: str, end_date: str) -> None:
    """
    采集基础数据
    :param start_date: 开始日期
    :param end_date: 结束日期
    :return:
    """
    logger.info(f"开始时间:{start_date}---结束时间:{end_date}")

    logger.info("-------------指数宽基行情------------")
    zskj()
    logger.info("-------------龙虎榜每日更新------------")
    today_lhb(start_date, end_date)
    logger.info("-------------融资融券每日更新------------")
    rzrq()
    logger.info("-------------公司动态每日更新------------")
    gsdt(start_date, end_date)
    logger.info("-------------龙虎榜个股每日更新------------")
    history_lhb(start_date, end_date)
    logger.info("-------------通达信风险数据采集------------")
    risk_tdx(start_date, end_date)
    logger.info("-------------同花顺 行业指数数据------------")
    industry_ths()
    logger.info("-------------同花顺 行业指数成分数据------------")
    industry_code_component_ths()


if __name__ == '__main__':
    start = time.time()

    deal_start_time = config_util.get_config("exe.history.base_collection.start_time")
    deal_end_time = config_util.get_config("exe.history.base_collection.end_time")

    get_base_collect(deal_start_time, deal_end_time)

    con.close()
    end = time.time()
    execution_time = end - start
    logger.info(f"代码执行时间为: {execution_time} 秒")
