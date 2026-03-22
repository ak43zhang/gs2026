"""
新华财网
"""

import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright
from sqlalchemy import create_engine

from gs2026.utils import mysql_util, config_util, log_util, email_util, string_util, display_config, string_enum
from gs2026.utils.pandas_display_config import set_pandas_display_options

logger = log_util.setup_logger(str(Path(__file__).absolute()))
set_pandas_display_options()

url = config_util.get_config("common.url")

engine = create_engine(url,pool_recycle=3600,pool_pre_ping=True)
con = engine.connect()
mysql_util = mysql_util.MysqlTool(url)
email_util = email_util.EmailUtil()
browser_path = string_enum.FIREFOX_PATH_1509


def collect_rmcx():
        with sync_playwright() as p:
            # 启动浏览器（headless=False 表示显示浏览器界面）
            # browser = p.chromium.launch(headless=False)
            # browser = p.firefox .launch(headless=False,executable_path=browser_path)
            browser = p.firefox.launch(headless=True,executable_path=browser_path)
            # browser = p.webkit .launch(headless=False)
            try:
                page = display_config.set_page_display_options_chrome(browser)

                page.goto("https://www.cnfin.com/flash/index.html",timeout=60000)
                time.sleep(1)

                all_news_data = []

                for i in range(1, 16):
                    header_elements = page.query_selector_all(f'div.ui-data-item:nth-child(1) > div:nth-child(2) > div:nth-child({i})')
                    for header in header_elements:
                        collect_content = header.inner_text()
                        # print("----------------------------")
                        # print(collect_content)
                        news_data = extract_news_from_text(collect_content, separator=" | ")

                        if news_data:
                            all_news_data.append(news_data)
                            print(f"  ✓ 成功提取: {news_data['标题'][:30]}...")
                        else:
                            print(f"  ✗ 提取失败")

                parsed_news = fix_cross_day_times(all_news_data)

                if parsed_news:
                    # 创建DataFrame
                    df = pd.DataFrame(parsed_news)
                    return df
                else:
                    print("未能提取到任何数据")
                    return pd.DataFrame()
            except Exception as e:
                print(e)
                return pd.DataFrame()
            finally:
                browser.close()  # 确保浏览器关闭

def fix_cross_day_times(news_list, base_date=None):
    """
    修复跨天时间问题

    参数:
        news_list: 包含发布时间(hh:mm)的字典列表
        base_date: 基准日期字符串(YYYY-MM-DD)或date对象

    返回:
        处理后的列表，发布时间更新为完整时间
    """
    if not news_list:
        return []

    # 确定基准日期
    if base_date is None:
        base_date = datetime.now().date()
    elif isinstance(base_date, str):
        base_date = datetime.strptime(base_date, "%Y-%m-%d").date()

    # 复制列表
    result = [item.copy() for item in news_list]

    # 按发布时间排序（假设列表已按时间顺序排列）
    # 如果需要，可以先排序：
    # result.sort(key=lambda x: x['发布时间'])

    # 处理时间
    current_date = base_date

    for i in range(len(result)):
        # 获取时间字符串
        time_str = result[i]['发布时间']

        # 解析时间
        try:
            hour, minute = map(int, time_str.split(':'))
        except:
            hour, minute = 0, 0

        # 对于第一条新闻，直接使用基准日期
        if i == 0:
            result[i]['发布时间'] = f"{current_date} {hour:02d}:{minute:02d}:00"
            continue

        # 获取上一条新闻的时间
        prev_time_str = result[i - 1]['发布时间']
        # 从完整时间字符串中提取时间部分
        prev_hour, prev_minute = map(int, prev_time_str.split(' ')[1].split(':')[:2])

        # 判断是否跨天
        # 简单规则：如果当前时间比上一条时间小很多，可能是下一天
        if hour < prev_hour - 12:
            # 跨天，日期加一天
            current_date += timedelta(days=1)

        result[i]['发布时间'] = f"{current_date} {hour:02d}:{minute:02d}:00"

    return result

def extract_news_from_text(news_text, separator=" | "):
    """
    从单个新闻文本中提取五个字段
    news_text格式示例：
    16:14
    标题行
    内容行...
    """
    try:
        lines = news_text.strip().split('\n')
        # 1. 提取时间（第一行）
        publish_time_ = lines[0]
        # 2. 提取标题（第二行）
        title_ = lines[1].split('。')[0]
        # 3. 提取内容（第三行）
        content_ = lines[1].strip()

        # 4. 生成内容hash
        content_hash_ = string_util.generate_md5(title_ + publish_time_)

        # 5. 出处（默认为人民财讯）
        source_ = "新华财网"

        # 返回字典
        return {
            '内容': content_,
            '发布时间': publish_time_,
            '标题': title_,
            '内容hash': content_hash_,
            '出处': source_,
            'analysis': ''
        }

    except Exception as e:
        print(f"处理文本时出错: {e}")
        print(f"问题文本: {news_text[:100]}...")
        return None

def filter_new_data(df: pd.DataFrame, existing_keys: set, key_column: str):
    """过滤出需要插入的新数据"""
    try:
        middle_df = df[~df[key_column].isin(existing_keys)]
        print(middle_df)
        return middle_df
    except KeyError as e:
        print("KeyError")
        return None

def safe_insert(df_new: pd.DataFrame, table_name: str, chunk_size=1000):
    """批量插入数据（自动处理异常）"""
    if df_new is None or df_new.empty :
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
        now_str = datetime.now().strftime('%Y%m%d')
        year = now_str[0:4]
        print("----------------当前时间：" + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + "----------------")
        table_name = 'news_cls'+year
        key_column = '内容hash'
        save2mysql(collect_rmcx(), table_name, key_column, '')
        time.sleep(polling_time)

if __name__ == "__main__":
    file_name = os.path.basename(__file__)

    # 主线程保持运行
    try:
        # 创建后台线程
        timer_thread = threading.Thread(target=time_task(600))
        timer_thread.daemon = True  # 设为守护线程
        timer_thread.start()

        while True:
            time.sleep(1)
    except Exception as e:
        logger.exception(f"采集流程失败: {e}")
        ERROR_TITLE = "异常告警"
        ERROR_CONTENT = f"{file_name} 执行异常: {str(e)}"
        FULL_HTML = email_util.full_html_fun(ERROR_TITLE, ERROR_CONTENT)
        for receiver_email in email_util.get_email_list():
            email_util.email_send_html(receiver_email, "异常告警", FULL_HTML)
        raise

# if __name__ == "__main__":
#     start = time.time()
#
#     df = collect_rmcx()
#     print(df)
#
#     end = time.time()
#     execution_time = end - start
#     print(f"代码执行时间为: {execution_time} 秒")