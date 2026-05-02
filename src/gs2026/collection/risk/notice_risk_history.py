"""
a股公告数据收集
    分析风险数据收集
"""
import re
import string
import time
from datetime import datetime
from pathlib import Path

import akshare as ak
import pandas as pd
from sqlalchemy import create_engine

from gs2026.tools import filters
from gs2026.utils import mysql_util, config_util, log_util, string_util
from gs2026.collection.risk.notice_content_fetcher import fetch_batch_content
from gs2026.utils.pandas_display_config import set_pandas_display_options

logger = log_util.setup_logger(str(Path(__file__).absolute()))
set_pandas_display_options()

url = config_util.get_config("common.url")
engine = create_engine(url,pool_recycle=3600,pool_pre_ping=True)
con = engine.connect()
mysql_tool = mysql_util.get_mysql_tool(url)



def hsjaggg(set_date):
    """
    沪深京 A 股公告
    :param set_date:
    :return:
    """
    try:
        df = ak.stock_notice_report(symbol='全部', date=set_date)
        df['内容hash']=(df["公告标题"].fillna("").astype(str) + df["公告日期"].fillna("").astype(str)).apply(string_util.generate_md5)
        df.columns = ['代码','名称','公告标题','公告类型','公告日期','网址','内容hash']
        return df
    except KeyError:
        logger.error("KeyError："+set_date)
        df = pd.DataFrame(columns=['代码','名称','公告标题','公告类型','公告日期','网址','内容hash'])
        return df

def notice_collect(start_time:str,end_time:str):
    key_column = '内容hash'
    day_sql = f"select trade_date from data_jyrl where  trade_date between '{start_time}' and '{end_time}' order by trade_date desc "
    day_df = pd.read_sql(day_sql, con=con)
    date_list = day_df.values.tolist()
    for date1 in date_list:
        set_date = date1[0]
        now_str = set_date.replace("-", "")
        year = set_date[:4]
        save_table_name = f'jhsaggg{year}'
        print("=====================沪深京 A 股公告时间：" + now_str)
        save2mysql(hsjaggg(now_str), save_table_name, key_column, '')
        # ★ 新增：采集完成后抓取公告原文（开关控制，默认关闭）
        if str(config_util.get_config('notice_content_fetcher.enabled', 'false')).lower() == 'true':
            try:
                fetch_batch_content(save_table_name, set_date)
            except Exception as e:
                logger.warning(f"公告原文抓取异常（不影响主流程）: {e}")

def save_notice_risk(notice_risk_time: str,table_name: str):
    """
    公告风险数据获取并存入mysql
    :param notice_risk_time:
    :param table_name:
    :return:
    """
    year = datetime.strptime(notice_risk_time, '%Y-%m-%d').year
    filter_df = filter_gg_jhsaggg(notice_risk_time, table_name)

    rows, columns = filter_df.shape
    print(f"----------------共{rows}条风险股票数据--------------------")
    # print(filter_df)

    risk_notice_table_name = f'wencaiquery_venture_{year}'

    # 原子操作
    if mysql_tool.check_table_exists(risk_notice_table_name):
        mysql_tool.delete_data(f"DELETE FROM `{risk_notice_table_name}` WHERE `风险类型`='公告风险' and trade_date='{notice_risk_time}'")
    with engine.begin() as conn:
        filter_df.to_sql(risk_notice_table_name, con=conn, if_exists='append', index=False)
        print("表名：" + risk_notice_table_name + "、数量：" + str(filter_df.shape[0]))


def filter_gg_jhsaggg(notice_risk_time:str, table_name: str):
    """
    过滤上一个工作日的公告中带风险词汇的过滤
    :param notice_risk_time:
    :param table_name:
    :return:
    """
    # 前后时间范围
    yes_sql = f"select trade_date from data_jyrl where trade_status=1 and trade_date<='{notice_risk_time}' order by trade_date desc limit 2"
    day_df = pd.read_sql(yes_sql, con=con)
    yes_day = day_df['trade_date'][0]
    n_days_before = day_df['trade_date'][1]

    print(str(n_days_before)+"-----------------"+str(yes_day))

    query = f"""SELECT 
                    CONVERT(`代码` USING utf8mb4) AS `代码`,
                    CONVERT(concat(`公告标题`,`公告类型`) USING utf8mb4) AS `公告标题`,
                    `公告日期`
                FROM {table_name} 
                where `公告日期`>='{n_days_before}' and `公告日期`<'{yes_day}'
               """

    df = pd.read_sql(query, con)

    # 中文标点处理（扩展标准标点符号）
    chinese_punctuation = '！“”￥…（）【】、；：‘’《》〈〉，。？'
    all_punctuation = string.punctuation + chinese_punctuation
    
    # 预处理函数
    def preprocess_text(text):
        # 去除所有中英文标点
        text_clean = text.translate(str.maketrans('', '', all_punctuation))
        return text_clean.lower()
    
    # 构建正则表达式模式
    pattern = r'(?:{})'.format('|'.join(map(re.escape, filters.RISK_KEYWORDS)))
    # print(pattern)
    
    # 过滤逻辑
    df['clean_title'] = df['公告标题'].apply(preprocess_text)
    mask = df['clean_title'].str.contains(pattern, regex=True)
    mid_df = df[mask][['代码', '公告标题','公告日期']].reset_index(drop=True)[['代码']].drop_duplicates()
    # print(mid_df)

    # 使用示例
    # filtered_df = dynamic_filter(middf1, "代码", ["600610", "603359", "002204","603949","600882","000601","600320","601328"])
    # print("-------------")
    # print(filtered_df)

    agdm_query = """select 
                        CONVERT(`stock_code` USING utf8mb4) AS `stock_code`,
                        CONVERT(`short_name` USING utf8mb4) AS `short_name`
                    from data_agdm
                """
    agdm_df = pd.read_sql(agdm_query, con)

    combine_df = pd.merge(
    left=mid_df[["代码"]],                 # 只保留A表的code字段
    right=agdm_df[["stock_code", "short_name"]],  # 只保留B表的目标字段
    left_on="代码",                       # A表的关联字段
    right_on="stock_code",                # B表的关联字段
    how="left"                            # 左关联模式
    ).dropna(subset=['stock_code'], axis=0)

    # print(combine_df)

    unique_df = combine_df.drop_duplicates().copy()
    filter_df = unique_df[unique_df['代码'].str.startswith(('00', '60')) & ~unique_df['short_name'].str.contains('退|ST')][['stock_code','short_name']]
    filter_df['风险类型']='公告风险'
    filter_df['trade_date'] = notice_risk_time
    filter_df.columns = ['代码','简称','风险类型','trade_date']
    # print(filter_df)

    return filter_df
    
#########################################################工具类################################################################################

def dynamic_filter(df, column, exclude_chars):
    pattern = r'(?:{})'.format('|'.join(map(re.escape, exclude_chars)))
    # print(pattern)
    return df[df[column].str.contains(pattern, case=False, regex=True, na=False)]

def filter_new_data(df: pd.DataFrame, existing_keys: set, key_column: str) -> pd.DataFrame:
    """过滤出需要插入的新数据"""
    mid_df = df[~df[key_column].isin(existing_keys)]
    return mid_df

def safe_insert(df_new: pd.DataFrame, table_name: str, chunk_size=1000):
    """批量插入数据（自动处理异常）"""
    if df_new.empty:
        print("没有需要插入的新数据")
        return
    
    rows, columns = df_new.shape
    print(f"----------------共{rows}条公告数据--------------------")

    try:
        with engine.begin() as conn:  # 自动事务管理
            df_new.to_sql(name=table_name, con=conn,if_exists='append', index=False,chunksize=chunk_size,method='multi')
            print("表名：" + table_name + "、数量：" + str(df_new.shape[0]))
    except Exception as e:
        print(f"数据插入失败: {str(e)}")
        # 可添加重试逻辑或错误日志记录

def save2mysql(df: pd.DataFrame,save_table_name: str, key_column: str, where_condition:str):
    existing_keys = mysql_tool.get_existing_keys(save_table_name, key_column,where_condition)
    df_new = filter_new_data(df, existing_keys, key_column)
    safe_insert(df_new, save_table_name)

#########################################################工具类################################################################################

def notice_risk_collect(deal_notice_risk_start_date, deal_notice_risk_end_date):
    deal_day_sql = f"select trade_date from data_jyrl where  trade_date between '{deal_notice_risk_start_date}' and '{deal_notice_risk_end_date}' and trade_status='1' order by trade_date desc "
    deal_day_df = pd.read_sql(deal_day_sql, con=con)
    days = deal_day_df.values.tolist()
    for day in days:
        deal_set_date = day[0]
        deal_year = datetime.strptime(deal_set_date, '%Y-%m-%d').year
        deal_table_name = f'jhsaggg{deal_year}'
        print("-----------------------" + deal_set_date + ",表名：" + deal_table_name)
        save_notice_risk(deal_set_date, deal_table_name)

def notice_and_risk_collect(
    start_date: str, 
    end_date: str
):
    """先执行公告采集，再执行公告风险采集。
    
    使用相同的日期参数，先采集公告数据，然后基于采集的数据进行风险分析。
    
    Args:
        start_date: 公告采集开始日期，格式 'YYYY-MM-DD'
        end_date: 公告采集结束日期，格式 'YYYY-MM-DD'
    
    """
    # 1. 先执行公告采集
    print(f"[INFO] 开始公告采集: {start_date} 至 {end_date}")
    notice_collect(start_date, end_date)
    
    # 2. 再执行公告风险采集（使用相同的日期参数）
    print(f"[INFO] 开始公告风险采集: {start_date} 至 {end_date}")
    notice_risk_collect(start_date, end_date)
    
    print("[INFO] 公告采集和风险采集全部完成")


if __name__ == "__main__":
    start = time.time()

    deal_notice_start_time = config_util.get_config("exe.history.notice_data.start_time")
    deal_notice_end_time = config_util.get_config("exe.history.notice_data.end_time")

    deal_notice_risk_start_time = config_util.get_config("exe.history.notice_risk_data.start_time")
    deal_notice_risk_end_time = config_util.get_config("exe.history.notice_risk_data.end_time")

    notice_collect(deal_notice_start_time, deal_notice_end_time)

    notice_risk_collect(deal_notice_risk_start_time, deal_notice_risk_end_time)


    con.close()

    end = time.time()
    execution_time = end - start
    print(f"代码执行时间为: {execution_time} 秒")