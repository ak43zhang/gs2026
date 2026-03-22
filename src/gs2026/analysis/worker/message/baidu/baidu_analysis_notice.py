"""
公告 百度ai分析消息
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
from config import display_config

from exe.history.risk.wencai_risk_history import db_retry
from sqlalchemy.exc import OperationalError, SAWarning
from playwright.sync_api import TimeoutError as SyncTimeoutError
from json.decoder import JSONDecodeError
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

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

def baidu_ai(query_list,table_name,analysis_table_name,_headless):
    start = time.time()
    query = ""
    count = len(query_list)
    for i in query_list:
        content_hash = i[0]
        title = i[1]
        notice_date = str(i[2])
        stock_code = i[3]
        child_query = "公告id："+content_hash+"，公告日期："+notice_date+"，"+"股票代码："+stock_code+"，标题为："+title
        query = query + child_query+"\n"
    query = query + f"""
                    请以顶级短线游资的角度分析上述"""+str(count)+"""条公告进行逐一分析，返回结果为json结构并且能够直接复制，json 结构为
                
			        {"公告集合": [
					    {
					        "公告id": "",
					        "公告日期": "",
					        "股票代码": "",
                            "风险大小": "",
                            "消息类型": "",
                            "判定依据":[""]
                        }   
					]}
                
                    其中，公告id字段只存一个id
                    风险大小字典值有重大，大，中，小四个。
                    消息类型的字典值有利好，利空，中性三个。
                    
                    请返回json结果。
            """
    # print(query)
    analysis = baidu_analysis(query,_headless)
    # print(analysis)

    # 先插入分析数据，再将处理后的表数据更新为已分析 analysis='1'
    if string_tool.is_valid_json(analysis) or analysis=='{}':
        update_sql = f"INSERT INTO  {analysis_table_name} (table_name,json_value) VALUES  ('{table_name}','{analysis}') "
        mysql_tool.update_data(update_sql)
    else:
        logger.error(table_name + "该数据ai分析失败，请重试")

    # 解析 JSON 字符串成json对象
    try:
        analysis_json = json.loads(analysis)
        ids = string_tool.extract_message_ids(analysis_json, "公告集合", "公告id")
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


# 抽出单独分析函数，用于错误重试
@db_retry(max_retries=30,initial_delay=1,max_delay=60,retriable_errors=(OperationalError, SyncTimeoutError,PlaywrightTimeoutError,JSONDecodeError,KeyError))
def baidu_analysis(query,_headless):
    # 启动时间
    print(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time())))
    # print(query)
    with sync_playwright() as p:
        # 启动浏览器（headless=False 表示显示浏览器界面）
        # browser = p.chromium.launch(headless=False)
        # browser = p.firefox.launch(headless=False, executable_path=browser_path)
        browser = p.firefox.launch(headless=_headless,executable_path=browser_path)
        # browser = p.webkit.launch(headless=False)

        page = display_config.set_page_display_options(browser)

        # 访问页面
        page.goto('https://chat.baidu.com/', timeout=page_timeout)

        # 等待页面加载（可能需要人工处理登录验证）
        # page.wait_for_selector('.input-wrap', timeout=page_timeout)

        # 实验跳过验证
        cs_input_selectors = ['#chat-input-box','#ai-input-editor','#chat-textarea']

        found_selector = wait_for_any_selector_simple(page, cs_input_selectors, timeout=20000)
        # print(found_selector)
        # time.sleep(100000)
        page.fill(found_selector, str(random.randint(2, 4)))
        if found_selector=='#chat-input-box' or found_selector=='#ai-input-editor':
            send_btn_selector = '#cs-bottom > div.chat-input-box-pc > div > div.input-wrap.input-wrap-multi-line > div.input-container.input-container-multi-line > div.cs-input-function-wrapper > div.cs-input-function-btn > i'
        if found_selector=='#chat-textarea':
            send_btn_selector = "#ci-submit-button-ai"

        # print(send_btn_selector)
        # time.sleep(100000)

        try:
            submit_button = page.wait_for_selector(send_btn_selector, state='visible', timeout=2000)
            submit_button.click()
        except PlaywrightTimeoutError:
            print(f"在指定时间内未找到可见的按钮元素 '{send_btn_selector}'，尝试使用回车键提交...")
            # 确保焦点在某个输入元素上，例如最后一个输入框
            page.focus(found_selector)
            # 模拟按下回车键
            page.keyboard.press('Enter')
            print("已模拟回车键操作。")

        # page.click(".pointer_vfmex_30")
        # page.wait_for_selector('.latest-rank_1j2mo_20 > span:nth-child(1) > i:nth-child(1)',timeout=page_timeout)
        page.wait_for_selector('._latest-rank_14pfw_20 > span:nth-child(1) > i:nth-child(1)', timeout=page_timeout)

        time.sleep(random.randint(1, 2))

        # 输入问题（选择器可能需要调整）
        input_selector = '#chat-textarea'  # 根据实际页面调整
        page.fill(input_selector, query)

        # 增加点击deepseekR1
        page.click(".model-toggle")

        # 点击发送按钮（可能需要更精确的选择器）
        # send_btn_selector = '#cs-bottom > div > div > div.input-wrap.input-wrap-multi-line > div.input-container.input-container-multi-line > div.cs-input-function-wrapper > div.cs-input-function-btn > i'  # 或使用class选择器
        send_btn_selector = '#ci-submit-button-ai'
        page.click(send_btn_selector)

        # 等待响应（时间根据网络情况调整）
        # page.wait_for_selector(
        #     '.latest-rank_1j2mo_20 > span:nth-child(1) > span:nth-child(1) > span:nth-child(1) > span:nth-child(1)',
        #     timeout=page_timeout)
        time.sleep(random.randint(1, 2))
        # time.sleep(100)
        # page.wait_for_selector('.answer-ask-container > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > span:nth-child(1)', timeout=page_timeout)
        page.wait_for_selector('._latest-rank_14pfw_20 > span:nth-child(1) > i:nth-child(1)', timeout=page_timeout)

        # 超时获取html，可放入日志中
        # print("--------------------------------")
        # print(page.content())
        # print("--------------------------------")

        # time.sleep(random.randint(10000, 50000))
        # 获取最新回复（需根据实际DOM结构调整）
        response_selectors = ['.hljs',]
        try:
            responses_text = '' # 使用默认值（避免分支遗漏）
            for selector in response_selectors:
                responses = page.query_selector(selector)
                if responses is not None:
                    responses_text = responses.inner_text()
                    break
            result = string_tool.remove_citation(responses_text).replace("‘", "(").replace("’", "）").replace("'", "")
            # print(result)

        except AttributeError as e:
            print(e)
            result = ''

        # 随机睡眠10s以内
        time.sleep(random.randint(2, 4))
        # 关闭浏览器
        browser.close()
        return result


def wait_for_any_selector_simple(page, selectors, timeout=3000):
    """
    轮询检测多个选择器中的任意一个

    :param page: 页面对象
    :param selectors: 选择器列表
    :param timeout: 超时时间（毫秒）
    :return: 第一个出现的元素句柄
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        for selector in selectors:
            element = page.query_selector(selector)
            if element:
                return selector
        page.wait_for_timeout(200)  # 短暂等待
    raise TimeoutError(f"在 {timeout}ms 内未找到任何选择器: {selectors}")



def get_notice_analysis(table_name,analysis_table_name,_headless):
    sql = f"select SQL_NO_CACHE `内容hash`,`公告标题`,`公告日期`,`代码` from {table_name} where analysis is null or analysis='' order by `公告日期` desc limit 20"
    with engine.connect() as conn:
        lists = pd.read_sql(sql, con=conn).values.tolist()
        if 0<len(lists)<15:
            sample_list = random.sample(lists, random.randint(0, len(lists)))
            baidu_ai(sample_list,table_name,analysis_table_name,_headless)
        if len(lists)>=15:
            sample_list = random.sample(lists, random.randint(12, 15))
            baidu_ai(sample_list,table_name,analysis_table_name,_headless)

def timer_task_do_notice():
    while True:
        get_notice_analysis("jhsaggg2024","analysis_notices",True)
        time.sleep(20)


if __name__ == "__main__":
    file_name = os.path.basename(__file__)

    # 主线程保持运行
    try:
        # 创建后台线程
        timer_thread1 = threading.Thread(target=timer_task_do_notice)
        timer_thread1.daemon = True  # 设为守护线程
        timer_thread1.start()

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        error_title = "异常告警"
        error_content = f"{file_name} 异常退出"
        full_html = email_tool.full_html_fun(error_title, error_content)
        for receiver_email in email_infomation.get_email_list():
            email_tool.email_send_html(receiver_email, "异常告警", full_html)
        print("任务已终止")

