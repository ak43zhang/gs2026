"""
涨停信息收集，用于收集【涨停，炸板】的首次涨停时间以及其他一些信息参数，用于分析打板哪种会出现炸板的问题
"""
import re
import time
import warnings
from typing import Optional, List

import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError, SAWarning
from loguru import logger

from gs2026.utils import mysql_util, config_util, display_config
from gs2026.utils.decorators_util import db_retry
from gs2026.utils.pandas_display_config import set_pandas_display_options
from gs2026.utils.wencai_cookie_config import load_wencai_context, has_cookie
from gs2026.constants import CHROME_1208

warnings.filterwarnings("ignore", category=SAWarning)

set_pandas_display_options()

url = config_util.get_config("common.url")

engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()
browser_path = CHROME_1208
mysql_tool = mysql_util.MysqlTool(url)

ROW_SELECTOR = '.iwc-table-body.scroll-style2 table tbody tr'
NUMBER_SELECTOR = '#xuan-top-con > div.xuangu-tool > div > div > div > span.ui-f24.ui-fb.red_text.ui-pl8'


def wencai_query_zt_zb(query: Optional[str] = None, headless: bool = True) -> pd.DataFrame:
    """
    问财查询涨停炸板数据

    Args:
        query: 查询条件
        headless: 是否无头模式

    Returns:
        查询结果DataFrame
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            executable_path=browser_path,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        # 使用Cookie创建上下文
        if has_cookie():
            logger.info("使用已保存的Cookie访问问财(zt_zb)")
            context = load_wencai_context(browser)
        else:
            logger.warning("未找到Cookie文件，将创建新会话")
            context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        
        page = context.new_page()
        page.goto("https://www.iwencai.com/unifiedwap/home/index")
        time.sleep(1)
        page.get_by_placeholder("请输入您的筛选条件，多个条件用分号隔开").fill(query)
        page.locator(".right-action > div:nth-child(3) > .icon").click()
        page.wait_for_selector(NUMBER_SELECTOR)
        logger.info("搜索结果加载成功")

        query_num = page.query_selector(NUMBER_SELECTOR).text_content()
        # 分页调整
        if int(query_num) > 50:
            page.locator(".drop-down-arrow").click()
            page.get_by_text("显示100条/页").click()
            time.sleep(1)  # 防止请求过快

        logger.info(f"查询条件：{query},查询数量：{query_num}")
        if query_num == '0':
            df = pd.DataFrame(columns=['代码', '简称', '风险类型'])
            return df

        # 等待表格加载
        page.wait_for_selector(ROW_SELECTOR)

        def remove_parentheses(text: str) -> str:
            """删除括号及括号内的内容"""
            return re.sub(r'\([^)]*\)', '', text).strip()

        # 获取表头
        table_headers = ["序号", "按钮", "股票代码", "股票简称"]
        header_elements = page.query_selector_all(
            '#iwc-table-container > div.iwc-table-content.isTwoLine > div.iwc-table-scroll > div.iwc-table-header.table-right-thead.scroll-style2 > ul > li'
        )
        for header in header_elements:
            lines = header.inner_text().split("\n")
            table_headers.append(remove_parentheses(lines[0]))

        # 定义采集数据的函数
        def extract_data() -> List[List[str]]:
            """获取页面中的数据"""
            rows = page.query_selector_all('.iwc-table-body.scroll-style2 table tbody tr')
            data = []
            for row in rows:
                cells = row.query_selector_all('td')
                row_data = [cell.inner_text() for cell in cells]
                data.append(row_data)
            return data

        # 采集当前页数据
        all_data = []
        current_page = 1

        while True:
            logger.info(f"正在采集第 {current_page} 页数据...")
            page_data = extract_data()
            all_data.extend(page_data)

            context_list = []
            # 检查是否有下一页
            li_elements = page.query_selector_all(
                '#iwcTableWrapper > div.xuangu-bottom-tool > div.pcwencai-pagination-wrap > div.pager > ul > li.disabled > a'
            )
            for i in li_elements:
                context_list.append(i.text_content())
            if_next_button = page.query_selector(
                '#iwcTableWrapper > div.xuangu-bottom-tool > div.pcwencai-pagination-wrap > div.pager > ul > li.disabled > a'
            )
            if (if_next_button is not None and if_next_button.text_content() == '下页') or \
               (len(li_elements) == 2 and any("下页" in item for item in context_list)):
                logger.info("已到达最后一页，采集结束。")
                break

            # 点击下一页
            next_button = page.query_selector(
                '#iwcTableWrapper > div.xuangu-bottom-tool > div.pcwencai-pagination-wrap > div.pager > ul > li:last-child > a'
            )
            next_button.click()
            time.sleep(1)  # 防止请求过快
            page.wait_for_selector('.iwc-table-body.scroll-style2 table tbody tr')
            current_page += 1

        # 关闭浏览器
        browser.close()

        # 返回采集到的所有数据
        df = pd.DataFrame(all_data, columns=table_headers)
        return df


def zt_zb_query(now_str: str) -> None:
    """
    查询涨停炸板数据

    Args:
        now_str: 当前日期字符串
    """
    query = f'{now_str}涨停或者炸板'
    table_name = 'wencaiquery_zt_zb'
    save_base_mysql(query, now_str, table_name)


@db_retry(max_retries=5, initial_delay=1, max_delay=60, retriable_errors=(OperationalError, TimeoutError, AttributeError))
def save_base_mysql(query: str, now_str: str, table_name: str) -> None:
    """
    保存基础数据到MySQL

    Args:
        query: 查询条件
        now_str: 当前日期字符串
        table_name: 表名
    """
    try:
        df = wencai_query_zt_zb(query)
        df['trade_date'] = now_str
        new_count = df.shape[0]

        # 计算比对
        sql = f"select * from `{table_name}` WHERE `trade_date`='{now_str}'"
        code_df = pd.read_sql(sql, con=con)
        old_count = code_df.shape[0]

        if df.empty:
            logger.error("wencaiquery_zt_zb未获取值")
        if new_count == old_count:
            logger.info(f"{now_str}涨停已采集完成,无需更新")
        else:
            if mysql_tool.check_table_exists(table_name):
                mysql_tool.delete_data(f"DELETE FROM `{table_name}` WHERE trade_date='{now_str}'")
            with engine.begin() as conn:
                df.to_sql(name=table_name, con=conn, if_exists='append', index=False)
                logger.info(f"表名：{table_name}、数量：{new_count}")
    except TimeoutError:
        logger.error("表格未显示，风险类型")
        raise
    except Exception:
        raise


def ztb_query(now_str: Optional[str] = None) -> None:
    """
    查询涨停数据

    Args:
        now_str: 当前日期字符串
    """
    table_name = 'ztb_day'
    query = f'{now_str}涨停'
    save_ztb_mysql(query, now_str, table_name)


def wencai_query_ztb(query: Optional[str] = None, now_str: Optional[str] = None, headless: bool = True) -> pd.DataFrame:
    """
    问财查询涨停数据

    Args:
        query: 查询条件
        now_str: 当前日期字符串
        headless: 是否无头模式

    Returns:
        查询结果DataFrame
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            executable_path=browser_path,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        # 使用Cookie创建上下文
        if has_cookie():
            logger.info("使用已保存的Cookie访问问财(zt_detail)")
            context = load_wencai_context(browser)
        else:
            logger.warning("未找到Cookie文件，将创建新会话")
            context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        
        page = context.new_page()

        page.goto("https://www.iwencai.com/unifiedwap/home/index")
        time.sleep(1)
        page.get_by_placeholder("请输入您的筛选条件，多个条件用分号隔开").fill(query)
        page.locator(".right-action > div:nth-child(3) > .icon").click()
        page.wait_for_selector(NUMBER_SELECTOR)
        logger.info("搜索结果加载成功")

        query_num = page.query_selector(NUMBER_SELECTOR).text_content()
        # 分页调整
        if int(query_num) > 50:
            page.locator(".drop-down-arrow").click()
            page.get_by_text("显示100条/页").click()
            time.sleep(1)  # 防止请求过快

        logger.info(f"查询条件：{query}查询数量：{query_num}")
        if query_num == '0':
            df = pd.DataFrame(columns=['代码', '简称', '风险类型'])
            return df

        # 等待表格加载
        page.wait_for_selector(ROW_SELECTOR)

        # 获取表头
        table_headers = ["序号", "按钮", "股票代码", "股票简称"]
        header_elements = page.query_selector_all(
            '#iwc-table-container > div.iwc-table-content.isTwoLine > div.iwc-table-scroll > div.iwc-table-header.table-right-thead.scroll-style2 > ul > li'
        )

        pattern = r'\n\d{4}\.\d{2}\.\d{2}|\([^)]*\)|\[[^]]*\]'
        for header in header_elements:
            lines = header.inner_text().split("\n")
            if len(lines) >= 3:
                common_part = lines[0]
                for _ in lines[1:]:
                    table_headers.append(f"{common_part}")
            else:
                table_headers.append(re.sub(pattern, '', header.inner_text()).replace(" ", ""))

        # 定义采集数据的函数
        def extract_data() -> List[List[str]]:
            """获取页面中的数据"""
            rows = page.query_selector_all('.iwc-table-body.scroll-style2 table tbody tr')
            data = []
            for row in rows:
                cells = row.query_selector_all('td')
                row_data = [cell.inner_text() for cell in cells]
                data.append(row_data)
            return data

        # 采集当前页数据
        all_data = []
        current_page = 1

        while True:
            logger.info(f"正在采集第 {current_page} 页数据...")
            page_data = extract_data()
            all_data.extend(page_data)

            context_list = []
            # 检查是否有下一页
            li_elements = page.query_selector_all(
                '#iwcTableWrapper > div.xuangu-bottom-tool > div.pcwencai-pagination-wrap > div.pager > ul > li.disabled > a'
            )
            for i in li_elements:
                context_list.append(i.text_content())
            if_next_button = page.query_selector(
                '#iwcTableWrapper > div.xuangu-bottom-tool > div.pcwencai-pagination-wrap > div.pager > ul > li.disabled > a'
            )
            if (if_next_button is not None and if_next_button.text_content() == '下页') or \
               (len(li_elements) == 2 and any("下页" in item for item in context_list)):
                logger.info("已到达最后一页，采集结束。")
                break

            # 点击下一页
            next_button = page.query_selector(
                '#iwcTableWrapper > div.xuangu-bottom-tool > div.pcwencai-pagination-wrap > div.pager > ul > li:last-child > a'
            )
            next_button.click()
            time.sleep(1)  # 防止请求过快
            page.wait_for_selector('.iwc-table-body.scroll-style2 table tbody tr')
            current_page += 1

        # 关闭浏览器
        browser.close()

        # 返回采集到的所有数据
        df = pd.DataFrame(all_data, columns=table_headers)
        df['trade_date'] = now_str
        return df


@db_retry(max_retries=5, initial_delay=1, max_delay=60, retriable_errors=(OperationalError, TimeoutError, AttributeError))
def save_ztb_mysql(query: str, now_str: str, table_name: str) -> None:
    """
    保存涨停数据到MySQL

    Args:
        query: 查询条件
        now_str: 当前日期字符串
        table_name: 表名
    """
    try:
        df = wencai_query_ztb(query, now_str)
        unique_df = df.drop_duplicates()
        new_count = unique_df.shape[0]

        # 计算比对
        sql = f"select * from `{table_name}` WHERE `trade_date`='{now_str}'"
        code_df = pd.read_sql(sql, con=con)
        old_count = code_df.shape[0]

        if unique_df.empty:
            logger.error(f"wencaiquery》》》{now_str}》》》未获取值")
        if new_count == old_count:
            logger.info(f"{now_str}涨停已采集完成,无需更新")
        else:
            if mysql_tool.check_table_exists(table_name):
                mysql_tool.delete_data(f"DELETE FROM `{table_name}` WHERE `trade_date`='{now_str}'")
            with engine.begin() as conn:
                unique_df.to_sql(name=table_name, con=conn, if_exists='append', index=False)
                conn.commit()
                logger.info(f"表名：{table_name}、数量：{new_count}")
    except TimeoutError:
        logger.error(f"表格未显示，数据类型：ztb")
        raise
    except Exception:
        raise


def collect_ztb_query(start_date: str, end_date: str) -> None:
    """
    问财涨停板数据

    Args:
        start_date: 开始日期
        end_date: 结束日期
    """
    ztb_query_day_sql = f"select trade_date from data_jyrl where trade_date between '{start_date}' and '{end_date}' and trade_status='1' order by trade_date desc "
    ztb_query_day_df = pd.read_sql(ztb_query_day_sql, con=con)
    ztb_query_days = ztb_query_day_df.values.tolist()
    for day in ztb_query_days:
        set_date = day[0]
        ztb_query(set_date)


def collect_zt_zb_collection(start_date: str, end_date: str) -> None:
    """
    问财涨停炸板数据

    Args:
        start_date: 开始日期
        end_date: 结束日期
    """
    zt_query_day_sql = f"select trade_date from data_jyrl where trade_date between '{start_date}' and '{end_date}' and trade_status='1' order by trade_date desc "
    zt_query_day_df = pd.read_sql(zt_query_day_sql, con=con)
    zt_query_days = zt_query_day_df.values.tolist()
    for day in zt_query_days:
        set_date = day[0]
        zt_zb_query(set_date)


if __name__ == "__main__":
    start = time.time()

    deal_ztb_query_start_time = config_util.get_config("exe.history", "")['ztb_query']['start_time']
    deal_ztb_query_end_time = config_util.get_config("exe.history", "")['ztb_query']['end_time']

    deal_base_query_start_time = config_util.get_config("exe.history", "")['zt_collection']['start_time']
    deal_base_query_end_time = config_util.get_config("exe.history", "")['zt_collection']['end_time']

    collect_ztb_query(deal_ztb_query_start_time, deal_ztb_query_end_time)
    collect_zt_zb_collection(deal_base_query_start_time, deal_base_query_end_time)

    con.close()

    end = time.time()
    execution_time = end - start
    logger.info(f"代码执行时间为: {execution_time} 秒")
