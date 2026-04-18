"""
收集财联社信息
"""

import os
import re
import time
from datetime import datetime
from pathlib import Path

from gs2026.utils.task_runner import run_daemon_task

import pandas as pd
import requests
from bs4 import BeautifulSoup
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

def get_cls(article_url):
    # 设置合法请求头
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
        'Referer': 'https://www.cls.cn/telegraph',
        'Accept-Language': 'zh-CN,zh;q=0.9'
    }

    try:
        # 发送请求（添加延时避免高频访问）
        time.sleep(1)
        response = requests.get(article_url, headers=headers, timeout=10)
        response.raise_for_status()

        # print(response.text)
        # 解析内容
        soup = BeautifulSoup(response.text, 'html.parser')
        # all_contents = soup.select('#__next > div > div.m-auto.w-1200 > div.clearfix.content-main-box > div.f-l.content-left > div:nth-child(2) > div')
        all_contents = soup.select('#__next > div > div.m-auto.w-1200 > div.clearfix.w-100p.p-t-20.p-b-30 > div.f-l.w-894 > div:nth-child(2) > div > div > div.clearfix.m-b-15.f-s-16.telegraph-content-box')
        # print(all_contents)
        content_lists = [content.text for content in all_contents if "【" in content.text]
        df = pd.DataFrame(content_lists, columns=["内容"])
        df['发布时间'] = df['内容'].apply(process_datetime)
        df['标题'] = df.apply(extract_text, axis=1)
        df['内容'] = df['内容'].str.replace(r'^\d{2}:\d{2}:\d{2}', '', regex=True)
        # 标题不唯一，做出时间后，使用时间+标题作为hash值
        df['内容hash'] = (df["标题"].fillna("").astype(str) + df["发布时间"].fillna("").astype(str)).apply(string_util.generate_md5)
        df['出处'] = '财联社'

        filtered_df = df[~df['内容'].str.contains('专享【', na=False)]
        # print(filtered_df)
        return filtered_df

    except Exception as e:
        print(f"抓取失败：{str(e)}")
        df = pd.DataFrame(columns=['内容','发布时间','标题', '内容hash', '出处'])
        return df


def process_datetime(row):
    """处理时间格式转换的核心函数"""
    # 提取日期部分（格式：YYYY.MM.DD）
    date_match = re.search(r'(\d{4}\.\d{2}\.\d{2})', row)
    if date_match:
        formatted_date = date_match.group(1).replace('.', '-')
    else:
        formatted_date = datetime.now().strftime('%Y-%m-%d')
    if formatted_date!=datetime.now().strftime('%Y-%m-%d'):
        formatted_date = datetime.now().strftime('%Y-%m-%d')

    # 提取时间部分（格式：HH:MM:SS）
    time_match = re.search(r'(\d{2}:\d{2}:\d{2})', row)
    formatted_time = time_match.group(1) if time_match else '00:00:00'

    return f"{formatted_date} {formatted_time}"

def extract_text(row):
    match = re.search(r'【(.*?)】', row['内容'])
    if match:
        return match.group(1)
    else:
        return row['内容'][:10] if len(row['内容']) >= 10 else row['内容']

def filter_new_data(df: pd.DataFrame, existing_keys: set, key_column: str) -> pd.DataFrame:
    """过滤出需要插入的新数据"""
    middf = df[~df[key_column].isin(existing_keys)]
    print(middf)
    return middf


def safe_insert(df_new: pd.DataFrame, table_name: str, chunk_size=1000):
    """批量插入数据（自动处理异常）"""
    if df_new.empty:
        print("没有需要插入的新数据")
        return

    rows, columns = df_new.shape
    print(f"----------------共{rows}条公告数据--------------------")

    try:
        with engine.begin() as conn:  # 自动事务管理
            df_new.to_sql(name=table_name, con=conn, if_exists='append', index=False, chunksize=chunk_size,method='multi')
        conn.close()
        print(f"成功插入{len(df_new)}条新数据")
    except Exception as e:
        print(f"数据插入失败: {str(e)}")
        # 可添加重试逻辑或错误日志记录


def save2mysql(df: pd.DataFrame, table_name: str, key_column: str, where_condition: str):
    existing_keys = mysql_util.get_existing_keys(table_name, key_column, where_condition)
    df_new = filter_new_data(df, existing_keys, key_column)
    safe_insert(df_new, table_name)

# polling_time 现成轮询时间
def time_task(polling_time):
    while True:
        article_url = "https://www.cls.cn/telegraph"
        now_str = datetime.now().strftime('%Y%m%d')
        year = now_str[0:4]
        print("----------------当前时间：" + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + "----------------")
        print(now_str)
        cls_table_name = 'news_cls'+year
        key_column = '内容hash'
        save2mysql(get_cls(article_url), cls_table_name, key_column, '')
        time.sleep(polling_time)


if __name__ == "__main__":
    run_daemon_task(target=time_task, args=(600,))
