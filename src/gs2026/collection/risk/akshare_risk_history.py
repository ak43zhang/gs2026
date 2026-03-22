"""
# #################################################################
#
# 基本面
# 统一返回风险数据的代码和简称
# 1.股份质押：质押比例大于百分之30
# 2.股东减持：前后20天
# 3.股东大会：未来10天开会的
# 4.商誉占比：商誉占净资产比例<=20% 【排除财务暴雷隐患】
# 5.预约披露时间：
#        巨潮资讯——防止黑天鹅事件暴雷【未来7天披露时间】
#        东方财富——防止黑天鹅事件暴雷【未来7天披露时间】
# 6.限售股解禁: 目前是前1个月后3个月，占解禁前流通市值比例1%
# 7.大宗交易: 前后一个月折价大于10%
# 8.高管减持：近一个月有过高管减持
# 9.业绩预告：公告日期在前后10天有业绩预告，且预告类型： 首亏|预减|增亏|续亏|不确定|略减
#
# 问财query 【主板，非st，总市值20亿到200亿，实际流通市值10亿到150亿，上市交易天数>180,股价大于3元,】
# 立案调查：        近1年被立案调查的股
# 机构持股：        机构持股占流通股比例>60%,机构持股家数>10家
# 分红派息:         未来2个月有分红
# 客户集中度:       前五大客户销售额占比大于40%
# 监管日期:         监管日期是近一个月
# 流动性风险_换手：  连续10天换手都小于1
# 流动性风险_换手2：  近20个交易日换手率小于20%
#
#
# 待确定
# 融资融券：
# 员工持股计划到期：        锁定期结束前30天
# 十大流通股东减持：        季度减持比例＞3%   发现减持公告后拉黑3个月（打板炸板后禁止低吸回补）
#
# #################################################################
#
# TODO 龙虎榜散户占比，分析近200日龙虎榜中龙虎榜占比较多的股票，可能进行过滤
# TODO 输入：代码，时间，   输出：代码，时间，次日开盘涨幅，次日最高涨幅，次日最低跌幅，次日收盘涨幅【分组，风险有效性验证】
#
#
# #################################################################
"""
import time
from datetime import datetime, timedelta
from pathlib import Path

import akshare as ak
import pandas as pd
from dateutil.relativedelta import relativedelta
from requests.exceptions import ChunkedEncodingError
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from urllib3.exceptions import ProtocolError

from gs2026.utils import mysql_util, config_util, log_util
from gs2026.utils.decorators_util import db_retry
from gs2026.utils.pandas_display_config import set_pandas_display_options

logger = log_util.setup_logger(str(Path(__file__).absolute()))
set_pandas_display_options()

url = config_util.get_config("common.url")
engine = create_engine(url,pool_recycle=3600,pool_pre_ping=True)
con = engine.connect()
mysql_tool = mysql_util.MysqlTool(url)


def gfzy(set_date):
    """
     股份质押 【质押比例大于百分之30】
     获取最新时间：https://data.eastmoney.com/gpzy/pledgeRatio.aspx
    :param set_date:
    :return:
    """
    day_sql = f"select trade_date from data_jyrl where  trade_date<='{set_date}'  order by trade_date desc limit 20"
    day_df = pd.read_sql(day_sql, con=con)
    sj_list = day_df.values.tolist()
    for b_day in sj_list:
        sj = b_day[0].replace("-", "")
        try:
            df = ak.stock_gpzy_pledge_ratio_em(date=sj)
            mid_df = df[df['质押比例'] >= 30][['股票代码', '股票简称']]
            mid_df['风险类型'] = '股份质押'
            mid_df.columns = ['代码', '简称', '风险类型']
            print("==========股份质押==========")
            # print(mid_df)
            return mid_df
        except Exception:
            logger.error(f"{sj}无数据")


def gdjc(set_date):
    """
    股东减持 【近一个月】
    :param set_date:
    :return:
    """
    df = ak.stock_ggcg_em(symbol="股东减持")
    df['变动截止日'] = pd.to_datetime(df['变动截止日'])
    df['公告日'] = pd.to_datetime(df['公告日'])

    # 确定未来 N 天的范围
    today = datetime.strptime(set_date, '%Y%m%d')
    n_days_before = today + timedelta(days=-20)
    n_days_later = today + timedelta(days=20)

    # 筛选数据
    mid_df = df[(df['变动截止日'] >= pd.Timestamp(n_days_before)) & (df['变动截止日'] <= pd.Timestamp(n_days_later)) & (
                df['公告日'] >= pd.Timestamp(n_days_before)) & (df['公告日'] <= pd.Timestamp(n_days_later))][
        ['代码', '名称']]
    mid_df['风险类型'] = '股东减持'
    mid_df.columns = ['代码', '简称', '风险类型']

    print("==========股东减持==========")
    # print(mid_df)

    return mid_df


def gddh(set_date):
    """
    股东大会 【规避】
    :param set_date:
    :return:
    """
    df = ak.stock_gddh_em()
    df['召开开始日'] = pd.to_datetime(df['召开开始日'])

    # 确定未来 N 天的范围
    today = datetime.strptime(set_date, '%Y%m%d')
    n_days_later = today + timedelta(days=10)

    # 筛选数据
    mid_df = df[(df['召开开始日'] >= pd.Timestamp(today)) & (df['召开开始日'] <= pd.Timestamp(n_days_later))][
        ['代码', '简称']]
    mid_df['风险类型'] = '股东大会'
    mid_df.columns = ['代码', '简称', '风险类型']

    print("==========股东大会==========")
    # print(mid_df)

    return mid_df


def syzb(set_date: str):
    """
    商誉占比 【排除财务暴雷隐患】商誉占净资产比例<=20%
    :param set_date:
    :return:
    """
    year = str(int(set_date[:4])-1)+'1231'
    print(year)
    df = ak.stock_sy_jz_em(date=year)
    mid_df = df[df['商誉占净资产比例'] >= 0.2][['股票代码', '股票简称']]
    mid_df['风险类型'] = '商誉占比'
    mid_df.columns = ['代码', '简称', '风险类型']

    print("==========商誉占比==========")
    # print(mid_df)
    return mid_df


def yyplsj_east(set_date: str):
    """
    预约披露时间_东方财富——防止黑天鹅事件暴雷【未来5天披露时间】
    :param set_date:
    :return:
    """
    day_sql = f"select trade_date from data_jyrl where  trade_date<='{set_date}' order by trade_date desc limit 130"
    day_df = pd.read_sql(day_sql, con=con)
    sj_list = day_df.values.tolist()
    for b_day in sj_list:
        sj = b_day[0].replace("-", "")
        try:
            df = ak.stock_yysj_em(symbol="沪深A股", date=sj)
            # print(df)
            # 计算每行的时间最大值
            date_columns = ['首次预约时间', '一次变更日期', '二次变更日期', '三次变更日期', '实际披露时间']
            for col in date_columns:
                df[col] = pd.to_datetime(df[col])
            df['max_date'] = df[date_columns].max(axis=1)

            # 确定时间范围
            today = datetime.strptime(set_date, '%Y-%m-%d')
            n_days_later = today + timedelta(days=5)

            # 筛选数据
            mid_df = df[(df['max_date'] >= pd.Timestamp(today)) & (df['max_date'] <= pd.Timestamp(n_days_later)) & (df['max_date'] > df['首次预约时间'])][['股票代码', '股票简称']]
            mid_df['风险类型'] = '预约披露时间_东方财富'
            mid_df.columns = ['代码', '简称', '风险类型']

            print("==========预约披露时间_东方财富==========")
            # print(mid_df)
            return mid_df
        except Exception:
            logger.error(f"{sj}无数据")


# def yyplsj_jczx(set_date: str):
#     """
#     预约披露时间_巨潮资讯——防止黑天鹅事件暴雷【未来5天披露时间】
#     """
#     df = ak.stock_report_disclosure(market="沪深京", period="2024年报")
#     # 计算每行的时间最大值
#     date_columns = ['首次预约', '初次变更', '二次变更', '三次变更', '实际披露']
#     for col in date_columns:
#         df[col] = pd.to_datetime(df[col])
#     df['max_date'] = df[date_columns].max(axis=1)
#     # 确定未来 N 天的范围
#     today = datetime.strptime(set_date, '%Y-%m-%d')
#     n_days_later = today + timedelta(days=5)
#
#     # 筛选数据
#     mid_df = df[(df['max_date'] >= pd.Timestamp(today)) & (df['max_date'] <= pd.Timestamp(n_days_later)) & (df['max_date'] > df['首次预约'])][['股票代码', '股票简称']]
#     mid_df['风险类型'] = '预约披露时间_巨潮资讯'
#     mid_df.columns = ['代码', '简称', '风险类型']
#
#     print("==========预约披露时间_巨潮资讯==========")
#     # print(mid_df)
#     return mid_df


def xsgjj(set_date: str):
    """
    限售股解禁 【目前是前1个月后3个月，占解禁前流通市值比例】
    比例：0.01
    :param set_date:
    :return:
    """
    # 获取当前日期
    today = datetime.strptime(set_date, '%Y%m%d')
    # 计算 1 个月前的日期
    one_month_ago = today - relativedelta(months=1)
    # 计算 3 个月后的日期
    three_months_later = today + relativedelta(months=3)

    # 格式化日期为 yyyyMMdd 格式
    one_month_ago_str = one_month_ago.strftime('%Y%m%d')
    three_months_later_str = three_months_later.strftime('%Y%m%d')
    df = ak.stock_restricted_release_detail_em(start_date=one_month_ago_str, end_date=three_months_later_str)
    mid_df = df[(df['占解禁前流通市值比例'] >= 0.01)][['股票代码', '股票简称']]
    mid_df['风险类型'] = '限售股解禁'
    mid_df.columns = ['代码', '简称', '风险类型']

    print("==========限售股解禁==========")
    # print(mid_df)
    return mid_df


def dzjy(set_date: str):
    """
    大宗交易 【折价90%】
    :param set_date:
    :return:
    """
    # 获取当前日期
    today = datetime.strptime(set_date, '%Y%m%d')
    # 计算 1 个月前的日期
    ago = today - relativedelta(months=1)
    # 计算 1 个月后的日期
    later = today + relativedelta(months=1)

    # 格式化日期为 yyyyMMdd 格式
    ago_str = ago.strftime('%Y%m%d')
    later_str = later.strftime('%Y%m%d')

    df = ak.stock_dzjy_mrtj(start_date=ago_str, end_date=later_str)
    mid_df = df[df['折溢率'] < -0.1][['证券代码', '证券简称']]
    mid_df['风险类型'] = '大宗交易'
    mid_df.columns = ['代码', '简称', '风险类型']

    print("==========大宗交易==========")
    # print(mid_df)
    return mid_df


def ggjc(set_date: str):
    """
    高管减持
    :param set_date:
    :return:
    """
    df = ak.stock_hold_management_detail_cninfo(symbol="减持")
    df['公告日期'] = pd.to_datetime(df['公告日期'])

    # 确定未来 N 天的范围
    today = datetime.strptime(set_date, '%Y%m%d')
    before = today + timedelta(days=-10)

    # 筛选数据
    mid_df = df[(df['公告日期'] >= pd.Timestamp(before)) & (df['公告日期'] <= pd.Timestamp(today))][['证券代码', '证券简称']]
    mid_df['风险类型'] = '高管减持'
    mid_df.columns = ['代码', '简称', '风险类型']

    print("==========高管减持==========")
    # print(mid_df)
    return mid_df


def yjyg(set_date: str):
    """
    业绩预告 【业绩预减的条件过滤】
    预告类型:['预增' '首亏' '预减' '减亏' '不确定' '增亏' '扭亏' '略增' '续盈' '略减' '续亏']
    :param set_date:
    :return:
    """
    day_sql = f"select trade_date from data_jyrl where  trade_date<='{set_date}'  order by trade_date desc limit 130"
    day_df = pd.read_sql(day_sql, con=con)
    date_list = day_df.values.tolist()
    for bday in date_list:
        sj = bday[0].replace("-", "")
        try:
            df = ak.stock_yjyg_em(date=sj)
            # print(df)
            df['公告日期'] = pd.to_datetime(df['公告日期'])

            # 前后时间范围
            today = datetime.strptime(set_date, '%Y-%m-%d')
            n_days_before = today + timedelta(days=-3)
            n_days_later = today + timedelta(days=5)
            # print(n_days_before,n_days_later)

            mid_df = df[df['预告类型'].str.contains('首亏|预减|增亏|续亏|不确定|略减') & (
                        df['公告日期'] >= pd.Timestamp(n_days_before)) & (df['公告日期'] <= pd.Timestamp(n_days_later))][['股票代码', '股票简称']]
            mid_df['风险类型'] = '业绩预告'
            mid_df.columns = ['代码', '简称', '风险类型']

            print("==========业绩预告==========")
            print(mid_df)
            return mid_df
        except Exception:
            logger.error(f"{sj}无数据")



@db_retry(max_retries=5,initial_delay=1,max_delay=60,retriable_errors=(OperationalError, TimeoutError,AttributeError,ProtocolError,ChunkedEncodingError))
def akshare_risk_get(risk_time: str):
    # 根据当前时期获得设定日期，设定日期为当前日期最近的一个交易日
    day_sql = f"select trade_date from data_jyrl where  trade_date<'{risk_time}' and trade_status='1' order by trade_date desc limit 1"
    day_df = pd.read_sql(day_sql, con=con)
    set_date_ = day_df.values.tolist()[0][0]
    set_date = day_df.values.tolist()[0][0].replace("-", "")
    year = datetime.strptime(risk_time, '%Y-%m-%d').year
    print("当前设置时间==========================================================================：" + risk_time)
    print("当前风险时间==========================================================================：" + set_date_)

    # 将多个 DataFrame 按行拼接
    # yyplsj_jczx(set_date) yyplsj_east(set_date_),没有历史数据
    combined_df = pd.concat(
        [
         gfzy(set_date_),       # 股份质押
         gddh(set_date),        # 股东大会
         xsgjj(set_date),       # 限售股解禁
         dzjy(set_date),        # 大宗交易
         yjyg(set_date_),       # 业绩预告
         gdjc(set_date),        # 股东减持
         syzb(set_date),        # 商誉占比
         ggjc(set_date)         # 高管减持
         ],
        ignore_index=True)

    # 去除重复的行
    unique_df = combined_df.drop_duplicates().copy()
    unique_df['trade_date'] = risk_time
    filter_df = unique_df[unique_df['代码'].str.startswith(('00', '60')) & ~unique_df['简称'].str.contains('退|ST')]

    rows, columns = filter_df.shape
    print(f"----------------共{rows}条风险股票数据--------------------")
    # print(filter_df)

    wencai_query_table_name = f'wencaiquery_venture_{year}'
    # print(wencai_query_table_name)

    # 原子操作
    if mysql_tool.check_table_exists(wencai_query_table_name):
        mysql_tool.delete_data(
            f"DELETE FROM `{wencai_query_table_name}` WHERE `风险类型` in ('股份质押','股东减持','股东大会','商誉占比','限售股解禁','大宗交易','高管减持','业绩预告') and trade_date='{risk_time}'")
            # f"DELETE FROM `{wencai_query_table_name}` WHERE `风险类型` in ('预约披露时间_东方财富','预约披露时间_巨潮资讯') and trade_date='{risk_time}'")
    with engine.begin() as conn:
        filter_df.to_sql(wencai_query_table_name, con=conn, if_exists='append', index=False)
        print("表名：" + wencai_query_table_name + "、数量：" + str(filter_df.shape[0]))


def akshare_risk_collect(start_date,end_date):
    # 多天
    deal_day_sql = f"select trade_date from data_jyrl where  trade_date between '{start_date}' and '{end_date}' and trade_status='1' order by trade_date desc "
    deal_day_df = pd.read_sql(deal_day_sql, con=con)
    days = deal_day_df.values.tolist()
    for day in days:
        deal_set_date = day[0]
        akshare_risk_get(deal_set_date)


if __name__ == "__main__":
    start = time.time()

    # 将当前日期格式化为 yyyy-MM-dd 字符串
    start_time = config_util.get_config("exe.history.akshare_risk_history.start_time")
    end_time = config_util.get_config("exe.history.akshare_risk_history.end_time")

    akshare_risk_collect(start_time, end_time)

    con.close()

    end = time.time()
    execution_time = end - start
    print(f"代码执行时间为: {execution_time} 秒")
