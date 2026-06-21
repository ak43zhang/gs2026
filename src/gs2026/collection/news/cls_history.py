"""
收集财联社信息 - Playwright 动态渲染版本
"""

import os
import re
import time
from datetime import datetime
from pathlib import Path

from gs2026.utils.task_runner import run_daemon_task

import pandas as pd
from sqlalchemy import create_engine

from gs2026.utils import mysql_util, config_util, log_util, email_util, string_util
from gs2026.utils.pandas_display_config import set_pandas_display_options


logger = log_util.setup_logger(str(Path(__file__).absolute()))
set_pandas_display_options()

url = config_util.get_config("common.url")

engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()
mysql_util = mysql_util.MysqlTool(url)
email_util = email_util.EmailUtil()


def get_cls(article_url):
    """使用 Playwright 动态渲染抓取财联社电报"""
    from playwright.sync_api import sync_playwright
    from gs2026.utils import string_enum

    try:
        p = sync_playwright().start()
        browser = p.firefox.launch(
            headless=True,
            executable_path=string_enum.FIREFOX_PATH_1509
        )
        page = browser.new_page()

        # 设置合理的请求头
        page.set_extra_http_headers({
            'Accept-Language': 'zh-CN,zh;q=0.9'
        })

        # 访问页面并等待内容加载
        page.goto(article_url, timeout=30000)

        # 等待电报内容元素渲染完成（新版页面类名）
        page.wait_for_selector('div.c-b.m-b-15.f-s-16', timeout=15000)
        time.sleep(2)  # 额外等待确保内容完全加载

        # 获取所有电报内容
        elements = page.query_selector_all('div.c-b.m-b-15.f-s-16')
        content_lists = []
        for el in elements:
            text = el.inner_text()
            if "【" in text:
                content_lists.append(text)

        browser.close()
        p.stop()

        # 无数据时返回空 DataFrame
        if not content_lists:
            logger.warning("[CLS] 未抓取到电报内容")
            return pd.DataFrame(columns=['内容', '发布时间', '标题', '内容hash', '出处'])

        df = pd.DataFrame(content_lists, columns=["内容"])
        df['发布时间'] = df['内容'].apply(process_datetime)
        df['标题'] = df.apply(extract_text, axis=1)
        df['内容'] = df['内容'].str.replace(r'^\d{2}:\d{2}:\d{2}', '', regex=True)
        df['内容hash'] = (df["标题"].fillna("").astype(str) + df["发布时间"].fillna("").astype(str)).apply(string_util.generate_md5)
        df['出处'] = '财联社'

        filtered_df = df[~df['内容'].str.contains('专享【', na=False)]
        return filtered_df

    except Exception as e:
        logger.error(f"[CLS] Playwright抓取失败：{str(e)}")
        return pd.DataFrame(columns=['内容', '发布时间', '标题', '内容hash', '出处'])


def process_datetime(row):
    """处理时间格式转换的核心函数"""
    # 提取日期部分（格式：YYYY.MM.DD）
    date_match = re.search(r'(\d{4}\.\d{2}\.\d{2})', row)
    if date_match:
        formatted_date = date_match.group(1).replace('.', '-')
    else:
        formatted_date = datetime.now().strftime('%Y-%m-%d')
    if formatted_date != datetime.now().strftime('%Y-%m-%d'):
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
            df_new.to_sql(name=table_name, con=conn, if_exists='append', index=False, chunksize=chunk_size, method='multi')
        print(f"成功插入{len(df_new)}条新数据")
    except Exception as e:
        print(f"数据插入失败: {str(e)}")


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
        cls_table_name = 'news_cls' + year
        key_column = '内容hash'
        save2mysql(get_cls(article_url), cls_table_name, key_column, '')
        time.sleep(polling_time)


if __name__ == "__main__":
    run_daemon_task(target=time_task, args=(600,))
