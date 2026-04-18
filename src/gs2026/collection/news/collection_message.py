"""
收集信息
    财经早餐-东财财富
    全球财经快讯-东财财富
    全球财经快讯-新浪财经
    快讯-富途牛牛
    全球财经直播-同花顺财经
    财经内容精选
"""

import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from gs2026.utils.task_runner import run_daemon_task

import akshare as ak
import pandas as pd
import requests
import swifter  # noqa
from bs4 import BeautifulSoup
from opencc import OpenCC
from sqlalchemy import create_engine

from gs2026.utils import mysql_util, config_util, log_util, email_util, string_util
from gs2026.utils.pandas_display_config import set_pandas_display_options


logger = log_util.setup_logger(str(Path(__file__).absolute()))
set_pandas_display_options()

url = config_util.get_config("common.url")

engine = create_engine(url,pool_recycle=3600,pool_pre_ping=True)
con = engine.connect()
mysql_util = mysql_util.MysqlTool(url)
email_util = email_util.EmailUtil()


def cjzc_dfcf():
    """
    财经早餐-东财财富
    :return:
    """
    try:
        df = ak.stock_info_cjzc_em()[:10]
        df['内容'] = df['链接'].apply(fetch_article_cjzc_dfcf)
        df['内容hash']=df["标题"].fillna("").astype(str).apply(string_util.generate_md5)
        df['出处']='财经早餐'
        mid_df=df[['标题','发布时间','内容','出处','内容hash']]
        # print(mid_df)

        return mid_df
    except Exception as e:
        print(f"财经早餐-东财财富抓取失败：{str(e)}")
        df = pd.DataFrame(columns=['标题','发布时间','内容','出处','内容hash'])
        return df

def fetch_article_cjzc_dfcf(url_str: str) -> str:
    """
    爬取东方财富网文章内容
    :param url_str: 文章地址，例如 "https://finance.eastmoney.com/a/202503203351572271.html"
    :return: 包含标题、正文、发布时间等信息的字典
    """
    # 设置合法请求头
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
        'Referer': 'https://finance.eastmoney.com/',
        'Accept-Language': 'zh-CN,zh;q=0.9'
    }

    try:
        # 发送请求（添加延时避免高频访问）
        time.sleep(1)
        response = requests.get(url_str, headers=headers, timeout=10)
        response.raise_for_status()

        # 解析内容
        soup = BeautifulSoup(response.text, 'html.parser')
        # 获取内容，过滤内容，使用换行拼接内容
        all_contents = soup.select('p')
        content_list = [contents.text for contents in all_contents if "\u3000\u3000" in contents.text]
        contents="\n".join(content_list)
        return contents

    except Exception as e:
        print(f"抓取失败：{str(e)}")
        return ''


def qqcjkx_dfcf():
    """
    全球财经快讯-东财财富
    :return:
    """
    try:
        df = ak.stock_info_global_em()
        df['内容hash']=df["标题"].fillna("").astype(str).apply(string_util.generate_md5)
        df['出处']='全球财经快讯-东财财富'
        mid_df=df[['标题','发布时间','摘要','出处','内容hash']].rename(columns={'摘要':'内容'})
        # print(mid_df)

        return mid_df
    except Exception as e:
        print(f"全球财经快讯-东财财富抓取失败：{str(e)}")
        df = pd.DataFrame(columns=['标题','发布时间','内容','出处','内容hash'])
        return df


def qqcjkx_xlcj():
    """
    全球财经快讯-新浪财经
    :return:
    """
    try:
        df = ak.stock_info_global_sina()
        df['内容hash']=df["内容"].fillna("").astype(str).apply(string_util.generate_md5)
        df['出处']='全球财经快讯-新浪财经'
        df['标题'] = df.apply(extract_text, axis=1)

        mid_df=df[['标题','时间','内容','出处','内容hash']].rename(columns={'时间':'发布时间'})
        # print(mid_df)

        return mid_df
    except Exception as e:
        print(f"全球财经快讯-新浪财经抓取失败：{str(e)}")
        df = pd.DataFrame(columns=['标题','发布时间','内容','出处','内容hash'])
        return df
   

def kx_ftnn():
    """
    快讯-富途牛牛
    :return:
    """
    converter = OpenCC('t2s')

    def convert_trad_to_simp(text):
        if pd.isna(text):  # 处理 NaN
            return text
        elif isinstance(text, str):
            return converter.convert(text)
        else:
            return str(text)  # 强制转换为字符串处理

    try:
        df = ak.stock_info_global_futu()
        df['内容hash']=df["内容"].fillna("").astype(str).apply(string_util.generate_md5)
        df['出处']='快讯-富途牛牛'
        # 使用 swifter 加速
        df['内容'] = df['内容'].swifter.apply(convert_trad_to_simp)
        df['标题'] = df['标题'].swifter.apply(convert_trad_to_simp)
        mid_df=df[['标题','发布时间','内容','出处','内容hash']]
        # print(mid_df)

        return mid_df
    except Exception as e:
        print(f"快讯-富途牛牛抓取失败：{str(e)}")
        df = pd.DataFrame(columns=['标题','发布时间','内容','出处','内容hash'])
        return df


def qqcjzb_thscj():
    """
    全球财经直播-同花顺财经
    :return:
    """
    try:
        df = ak.stock_info_global_ths()
        df['内容hash']=df["内容"].fillna("").astype(str).apply(string_util.generate_md5)
        df['出处']='全球财经直播-同花顺财经'

        mid_df=df[['标题','发布时间','内容','出处','内容hash']]
        # print(mid_df)

        return mid_df
    except Exception as e:
        print(f"全球财经直播-同花顺财经抓取失败：{str(e)}")
        df = pd.DataFrame(columns=['标题','发布时间','内容','出处','内容hash'])
        return df


# def zqyc_xlcj():
#     """
#     证券原创-新浪财经
#     """
#     try:
#         df = ak.stock_info_broker_sina(page="1")
#         df['内容hash']=df["内容"].fillna("").astype(str).apply(StringTool.generate_md5)
#         df['出处']='zqyc_xlcj'
#         df['标题'] = df.apply(extract_text, axis=1)
#         df['时间'] = pd.to_datetime(df['时间'], format='%Y年%m月%d日 %H:%M').dt.strftime('%Y-%m-%d %H:%M:%S')
#
#         middf=df[['标题','时间','内容','出处','内容hash']].rename(columns={'时间':'发布时间'})
#         # print(middf)
#
#         return middf
#     except Exception as e:
#         print(f"证券原创-新浪财经抓取失败：{str(e)}")
#         df = pd.DataFrame(columns=['标题','发布时间','内容','出处','内容hash'])
#         return df


def cjnrjx(set_date):
    """
    财经内容精选
    :param set_date:
    :return:
    """
    try:
        df = ak.stock_news_main_cx()
        df['pub_time'] = pd.to_datetime(df['pub_time'])

        # 确定未来 N 天的范围
        today = datetime.strptime(set_date, '%Y%m%d')
        n_days_before = today + timedelta(days=-3)
        n_days_later = today + timedelta(days=3)

        mid_df = df[(df['pub_time'] >= pd.Timestamp(n_days_before)) & (df['pub_time'] <= pd.Timestamp(n_days_later))][['tag','pub_time','summary']]
        mid_df['出处']='财新数据'
        mid_df['内容hash']=df['summary'].apply(string_util.generate_md5)
        mid_df.columns = ['标题','时间','内容','出处','内容hash']
        # print(mid_df)
        return mid_df
    except Exception as e:
        print(f"抓取失败：{str(e)}")
        df = pd.DataFrame(columns=['标题','时间','内容','出处','内容hash'])
        return df


def combine_message():
    # 将多个 DataFrame 按行拼接     删除 zqyc_xlcj()
    combined_df = pd.concat([cjzc_dfcf(), qqcjkx_dfcf(),qqcjkx_xlcj(),kx_ftnn(),qqcjzb_thscj()], ignore_index=True)
    combined_filter_df=combined_df[combined_df['发布时间'].astype(str).str.contains('2026')]

    return combined_filter_df


#########################################################工具类################################################################################
def extract_text(row):
    match = re.search(r'【(.*?)】', row['内容'])
    if match:
        return match.group(1)
    else:
        return row['内容'][:10] if len(row['内容']) >= 10 else row['内容']

def filter_new_data(df: pd.DataFrame, existing_keys: set, key_column: str) -> pd.DataFrame:
    """过滤出需要插入的新数据"""
    mid_df = df[~df[key_column].isin(existing_keys)]
    if not mid_df.empty:
        print(mid_df)
    return mid_df

def safe_insert(df_new: pd.DataFrame, table_name: str, chunk_size=1000):
    """批量插入数据（自动处理异常）"""
    if df_new.empty:
        print("没有需要插入的新数据")
        return
    
    rows, columns = df_new.shape
    print(f"共{rows}条公告数据")

    try:
        with engine.begin() as conn:  # 自动事务管理
            df_new.to_sql(name=table_name, con=conn,if_exists='append', index=False,chunksize=chunk_size,method='multi')
        print(f"成功插入{len(df_new)}条新数据")
    except Exception as e:
        print(f"数据插入失败: {str(e)}")
        # 可添加重试逻辑或错误日志记录

#########################################################工具类################################################################################

def save2mysql(df: pd.DataFrame,table_name: str, key_column: str, where_condition:str):
    existing_keys = mysql_util.get_existing_keys(table_name, key_column,where_condition)
    df_new = filter_new_data(df, existing_keys, key_column)
    safe_insert(df_new, table_name)

#########################################################线程类################################################################################
def time_task(polling_time):
    while True:
        now_str = datetime.now().strftime('%Y%m%d')
        year = now_str[0:4]
        print("----------------当前时间："+ datetime.now().strftime('%Y-%m-%d %H:%M:%S')+"----------------")
        print(now_str)
        key_column='内容hash'
        #--------------------------------------------------------------------
        combine_message_table_name='news_combine'+year
        combine_message_df = combine_message()
        save2mysql(combine_message_df,combine_message_table_name, key_column,'')
        combine_message_df.drop(combine_message_df.index, inplace=True)

        time.sleep(polling_time)

if __name__ == "__main__":
    run_daemon_task(target=time_task, args=(600,))
