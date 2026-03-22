"""百度ai分析消息 v3版本。
一次性分析N条数据，暂定5条，然后增加消息id到json中，最后分析完同时存入这N条数据
主要是增加分析效率
"""
import pandas as pd
import time
from sqlalchemy import create_engine
import warnings
import os

from adatacollection.tools import mysql_tool
from adatacollection.tools import email_tool
from gs2026.utils.config_util import get_config
from adatacollection.tools import string_tool
from adatacollection.tools import string_enum
from adatacollection.dic import email_infomation
from exe.tools import log_tool
from config import pandas_display_config
from pathlib import Path

from sqlalchemy.exc import SAWarning
from json.decoder import JSONDecodeError
import baidu_analysis_notice

import json
import random
import threading

warnings.filterwarnings("ignore", category=SAWarning)

logger = log_tool.setup_logger(str(Path(__file__).absolute()))
pandas_display_config.set_pandas_display_options()

config = get_config
url = config_util.get_config("common.url")

engine = create_engine(url,pool_recycle=3600,pool_pre_ping=True)
con = engine.connect()
browser_path = string_enum.FIREFOX_PATH_1509
mysql_util = mysql_util.MysqlTool(url)
email_tool = email_tool.EmailTool()

page_timeout = 360000


def baidu_ai(query_list, table_name, analysis_table_name,_headless):
    start = time.time()
    query = ""
    count = len(query_list)
    for i in query_list:
        content_hash = i[0]
        content = i[1]
        child_query = "消息id：" + content_hash + ",消息内容：" + content
        query = query + child_query + "\n"
    query = query + f"""
                    请以顶级短线游资的角度分析上述""" + str(count) + """条消息进行逐一分析，返回结果为json对象，json 结构为

			        {"消息集合": [
					    "消息id": "",
                        "板块详情": [
                            {
                                "板块名称": "",
                                "板块明细": [
                                    {
                                        "a股代码": "",
                                        "a股名称": "",
                                        "关联原因": "",
                                        "利好利空": ""
                                    }
                                    ]
                                }
                            ],
                        "消息大小": "",
                        "消息类型": "",
                        "涉及板块": [""],
                        "龙头个股": [""]
					]}

                    其中，消息id字段只存一个id
                    消息大小是对a股市场影响程度的字典值有重大，大，中，小四个。
                    消息类型的字典值有利好，利空，中性三个。
                    利好利空的字典值有利好，利空，中性三个,龙头个股存放的只有6位数的股票代码。
                    
                    请返回json结果。
            """
    # print(query)
    analysis = baidu_analysis_notice.baidu_analysis(query, _headless)
    # print(analysis)
    analysis = string_tool.remove_json_prefix(analysis, 'json')
    analysis = string_tool.remove_json_prefix(analysis, 'Copy')
    analysis = string_tool.remove_json_prefix(analysis, 'Code')
    analysis = string_tool.remove_json_comments(analysis)
    analysis = analysis.lstrip()
    json_data, remaining_text = string_tool.extract_json_from_string(analysis)

    # 先插入分析数据，再将处理后的表数据更新为已分析 analysis='1'
    if string_tool.is_valid_json(json_data):
        update_sql = f"INSERT INTO  {analysis_table_name} (table_name,json_value) VALUES  ('{table_name}','{json_data}') "
        mysql_tool.update_data(update_sql)
    else:
        logger.error(table_name + "该数据ai分析失败，请重试")

    # 解析 JSON 字符串成json对象
    try:
        analysis_json = json.loads(json_data)
        ids = string_tool.extract_message_ids(analysis_json, "消息集合", "消息id")
        ids_count = len(ids)
        if ids_count > 0:
            ids_str = "(" + ",".join(f"'{item}'" for item in ids) + ")"
            update_sql = f"UPDATE {table_name} SET analysis='1' WHERE `内容hash` in {ids_str}"
            mysql_tool.update_data(update_sql)
        print(f"更新{table_name}表{len(ids)}条数据，更新id：", ids)
    except JSONDecodeError:
        logger.error("json解析失败,JSONDecodeError")
    except KeyError:
        logger.error("json解析失败,KeyError")

    end = time.time()
    execution_time = end - start
    print(f"{table_name}AI分析耗时: {execution_time} 秒")


def get_news_financial_analysis(table_name,analysis_table_name,_headless):
    sql = f"select SQL_NO_CACHE `内容hash`,`内容` from {table_name} where analysis is null or analysis='' order by `时间` desc limit 20"
    with engine.connect() as conn:
        lists = pd.read_sql(sql, con=conn).values.tolist()
        if len(lists) >= 10:
            sample_list = random.sample(lists, random.randint(5, 10))
            baidu_ai(sample_list,table_name,analysis_table_name,_headless)

def time_task_do_financial(polling_time):
    while True:
        get_news_financial_analysis("news_financial","analysis_news",True)
        time.sleep(polling_time)

if __name__ == "__main__":
    file_name = os.path.basename(__file__)

    try:
        timer_thread = threading.Thread(target=time_task_do_financial(2))
        timer_thread.daemon = True  # 设为守护线程
        timer_thread.start()

        # 主线程保持运行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        error_title = "异常告警"
        error_content = f"{file_name} 异常退出"
        full_html = email_tool.full_html_fun(error_title, error_content)
        for receiver_email in email_infomation.get_email_list():
            email_tool.email_send_html(receiver_email, "异常告警", full_html)
        print("任务已终止")

