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

def baidu_ai(query_list,table_name,analysis_table_name,_headless):

    for i in query_list:
        start = time.time()
        gpjc = i[0]
        sj = i[1]
        gpjc_sj_id = string_tool.generate_md5(gpjc+sj)
        query = sj+gpjc+"""涨停受到哪些消息影响，这些消息分别最早出现在哪天，以及未来可能影响涨停的预期消息，预期消息是否有延续性（是，否）,只给出前后5天的消息，请将结果简练成时间，消息简化到能准确知道是什么事件，消息简化在15个字以内，
        该股票的股性做超短是否会套人,
        该涨停受到什么板块消息刺激而涨停,
        该涨停受到什么概念消息刺激而涨停,
        该涨停受到哪个龙头股的消息刺激而涨停。
        返回结果为json对象，json 结构为：
        {
            "股票名称"："",
            "涨停时间":"",
            "板块消息":["板块":"","板块刺激消息":[""]],
            "概念消息":["概念":"","概念刺激消息":[""]],
            "龙头股消息":["龙头股":"","龙头股刺激消息":[""]],
            "消息":["影响消息":"","最早出现时间":""],
            "预期涨停消息":["预期消息":"","最早出现时间":""，"延续性":""]
        }
        
        请返回json结果。
        """

        # print(query)
        analysis = baidu_analysis_notice.baidu_analysis(query, _headless)
        # print(analysis)

        # 先插入分析数据，再将处理后的表数据更新为已分析 analysis='1'
        analysis = string_tool.remove_json_prefix(analysis, 'json')
        analysis = string_tool.remove_json_prefix(analysis, 'Copy')
        analysis = string_tool.remove_json_prefix(analysis, 'Code')
        analysis = string_tool.remove_json_comments(analysis)
        analysis = analysis.lstrip()
        json_data, remaining_text = string_tool.extract_json_from_string(analysis)

        if string_tool.is_valid_json(json_data):
            update_sql = f"INSERT INTO  {analysis_table_name} (gpjc_sj_id,gpjc,sj,json_data) VALUES  ('{gpjc_sj_id}','{gpjc}','{sj}','{json_data}') "
            mysql_tool.update_data(update_sql)
        else:
            logger.error(table_name + "该数据ai分析失败，请重试")
            # print(analysis)

        # 解析 JSON 字符串成json对象
        try:
            update_sql = f"UPDATE {table_name} SET analysis='1' WHERE `股票简称`='{gpjc}' and `trade_date`='{sj}'"
            mysql_tool.update_data(update_sql)
            print(f"更新{table_name}表1条数据，更新id：",gpjc_sj_id)
        except JSONDecodeError:
            logger.error("json解析失败,JSONDecodeError")
        except KeyError:
            logger.error("json解析失败,KeyError")


        end = time.time()
        execution_time = end - start
        print(f"{table_name}AI分析耗时: {execution_time} 秒")

def get_news_ztb_analysis(table_name,analysis_table_name,_headless):
    sql = f"select SQL_NO_CACHE `股票简称`,`trade_date` from {table_name} where (analysis is null or analysis='') order by `trade_date` desc limit 20"
    with engine.connect() as conn:
        lists = pd.read_sql(sql, con=conn).values.tolist()
        if len(lists) >= 15:
            sample_list = random.sample(lists, random.randint(10, 15))
            baidu_ai(sample_list, table_name ,analysis_table_name,_headless)

def time_task_do_ztb(polling_time):
    while True:
        get_news_ztb_analysis("ztb_day","analysis_ztb",True)
        time.sleep(polling_time)

if __name__ == "__main__":
    file_name = os.path.basename(__file__)

    try:
        # 创建后台线程
        timer_thread = threading.Thread(target=time_task_do_ztb(20))
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
