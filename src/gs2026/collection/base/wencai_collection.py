"""
问财收集信息
    基础数据——某天经过初筛的基础数据
    热股数据——同花顺热门数据
"""
import re
import time
import warnings
from datetime import datetime

import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError, SAWarning
from loguru import logger

from gs2026.utils import mysql_util, config_util, display_config
from gs2026.utils.decorators_util import db_retry
from gs2026.utils.pandas_display_config import set_pandas_display_options
from gs2026.constants import CHROME_1208

warnings.filterwarnings("ignore", category=SAWarning)

set_pandas_display_options()

url = config_util.get_config("common.url")

engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()
browser_path = CHROME_1208
mysql_util = mysql_util.MysqlTool(url)

ROW_SELECTOR = '.iwc-table-body.scroll-style2 table tbody tr'
DISABLED_SELECTOR = '#iwcTableWrapper > div.xuangu-bottom-tool > div.pcwencai-pagination-wrap > div.pager > ul > li.disabled > a'
LAST_ITEM_SELECTOR = '#iwcTableWrapper > div.xuangu-bottom-tool > div.pcwencai-pagination-wrap > div.pager > ul > li:last-child > a'
HEADER_SELECTOR = '#iwc-table-container > div.iwc-table-content.isTwoLine > div.iwc-table-scroll > div.iwc-table-header.table-right-thead.scroll-style2 > ul > li'
NUMBER_SELECTOR = '#xuan-top-con > div.xuangu-tool > div > div > div > span.ui-f24.ui-fb.red_text.ui-pl8'

def wencai_page_collection(page,query,fxlx):
    page.goto("https://www.iwencai.com/unifiedwap/home/index")
    time.sleep(1)
    page.get_by_placeholder("请输入您的筛选条件，多个条件用分号隔开").fill(query)
    page.locator(".right-action > div:nth-child(3) > .icon").click()
    page.wait_for_selector(NUMBER_SELECTOR)
    logger.info("搜索结果加载成功")

    query_num = page.query_selector(NUMBER_SELECTOR ).text_content()
    # 分页调整
    if int(query_num) > 50:
        page.locator(".drop-down-arrow").click()
        page.get_by_text("显示100条/页").click()
        time.sleep(1)  # 防止请求过快

    logger.info("风险类型：" + fxlx + ",查询数量：" + query_num)
    if query_num == '0':
        df = pd.DataFrame(columns=['代码', '简称', '风险类型'])
        return df

    # 等待表格加载
    page.wait_for_selector(ROW_SELECTOR)

    # 获取表头
    table_headers = ["序号", "按钮", "股票代码", "股票简称"]
    header_elements = page.query_selector_all(HEADER_SELECTOR)
    for header in header_elements:
        lines = header.inner_text().split("\n")
        if len(lines) >= 3:
            # 提取公共部分和日期部分
            common_part = lines[0]
            for line in lines[1:]:
                table_headers.append(f"{common_part}\n{line}")
        else:
            table_headers.append(header.inner_text())


    # 采集当前页数据
    all_data = []
    current_page = 1

    while True:
        print(f"正在采集第 {current_page} 页数据...")
        page_data = extract_data_fast(page)
        all_data.extend(page_data)
        print(f"第 {current_page} 页采集完成，已采集 {len(all_data)} 条数据")

        context_list = []
        # 检查是否有下一页
        li_elements = page.query_selector_all(DISABLED_SELECTOR)
        for i in li_elements:
            context_list.append(i.text_content())
        if_next_button = page.query_selector(DISABLED_SELECTOR)  # 使用 Playwright 特有的选择器
        if (if_next_button is not None and if_next_button.text_content() == '下页') or (
                len(li_elements) == 2 and any("下页" in item for item in context_list)):
            print("已到达最后一页，采集结束。")
            break

        # 点击下一页
        next_button = page.query_selector(LAST_ITEM_SELECTOR)
        next_button.click()
        time.sleep(1)  # 防止请求过快
        page.wait_for_selector(ROW_SELECTOR)  # 等待新页面加载完成
        current_page += 1
    # 返回采集到的所有数据
    df = pd.DataFrame(all_data, columns=table_headers)[['股票代码', '股票简称']]
    df['风险类型'] = fxlx
    df.columns = ['代码', '简称', '风险类型']
    return df

def wencai_query_base(query: str = None,fxlx: str=None,headless=True):
    with sync_playwright() as p:
        # 启动浏览器（headless=False 表示显示浏览器界面）
        # browser = p.chromium.launch(headless=False,executable_path=browser_path,args=['--disable-blink-features=AutomationControlled'])
        browser = p.chromium.launch(headless=headless,executable_path=browser_path,args=['--disable-blink-features=AutomationControlled'])
        page = display_config.set_page_display_options_chrome(browser)
        # 打开 i问财 页面
        result_df = wencai_page_collection(page, query, fxlx)

        # 关闭浏览器
        browser.close()

        return result_df

def base_query(now_str: str):
    # 计算时间
    date_sql = f"select trade_date from  ((select trade_date from data_jyrl where trade_status=1 and trade_date<='{now_str}' order by trade_date desc limit 400) union (select trade_date from data_jyrl where trade_status=1 and trade_date>'{now_str}' order by trade_date  limit 2)) as ta1 order by trade_date desc limit 400"
    day_df = pd.read_sql(date_sql, con=con)
    zt = day_df['trade_date'][3]
    qt = day_df['trade_date'][4]
    two_months_ago = day_df['trade_date'][41]
    one_year_ago = day_df['trade_date'][321]

    # 计算中小盘指数和
    zs_sql = f"select sum(change_pct) as zshb from data_zshq_ths where index_code ='399401' and trade_date in ('{zt}','{qt}') limit 10"
    zs_df = pd.read_sql(zs_sql, con=con)
    zshb = round(zs_df['zshb'][0]+2, 2)

    year = str(datetime.strptime(now_str, '%Y-%m-%d').year)

    query = f'主板，非st，{zt}总市值20亿到400亿，{zt}实际流通市值小于350亿，{zt}上市交易天数>180天,{one_year_ago}到{zt}最低价大于2.5元,{two_months_ago}到{zt}涨停次数大于0,{qt}到{zt}区间涨跌幅<={zshb}'
    table_name = 'wencaiquery_basequery_' + year
    logger.info(query+"\n"+table_name+"\n"+now_str)
    fxlx = '无'
    save_base_mysql(query,now_str,fxlx,table_name)


@db_retry(max_retries=5,initial_delay=1,max_delay=60,retriable_errors=(OperationalError, TimeoutError,AttributeError))
def save_base_mysql(query:str,now_str:str,fxlx:str,table_name:str):
    try:
        df = wencai_query_base(query, fxlx)
        df['trade_date'] = now_str
    except TimeoutError:
        logger.error("表格未显示，风险类型：" + fxlx)
        raise
    except Exception:
        # 捕获其他异常类型
        raise

    if df.empty:
        logger.error("wencai_query_basequery》》》" + fxlx + "》》》未获取值")
    else:
        if mysql_util.check_table_exists(table_name):
            mysql_util.delete_data(f"DELETE FROM `{table_name}` WHERE `风险类型`='无' and trade_date='{now_str}'")
        with engine.begin() as conn:
            df.to_sql(name=table_name, con=conn, if_exists='append', index=False)
            print("表名：" + table_name + "、数量：" + str(df.shape[0]))


def wencai_query_popularity(query: str = None,now_str: str=None):
    with sync_playwright() as p:
        # 启动浏览器（headless=False 表示显示浏览器界面）
        # browser = p.chromium.launch(headless=False,executable_path=browser_path,args=['--disable-blink-features=AutomationControlled'])
        browser = p.chromium.launch(headless=True, executable_path=browser_path,args=['--disable-blink-features=AutomationControlled'])

        page = display_config.set_page_display_options_chrome(browser)

        # 打开 i问财 页面
        page.goto("https://www.iwencai.com/unifiedwap/home/index")
        time.sleep(1)
        page.get_by_placeholder("请输入您的筛选条件，多个条件用分号隔开").fill(query)
        page.locator(".right-action > div:nth-child(3) > .icon").click()
        page.wait_for_selector(ROW_SELECTOR)
        logger.info("搜索结果表格加载成功")

        query_num = page.query_selector(NUMBER_SELECTOR).text_content()
        # 分页调整
        if int(query_num) > 50:
            page.locator(".drop-down-arrow").click()
            page.get_by_text("显示100条/页").click()
            time.sleep(1)  # 防止请求过快

        logger.info("查询数量：" + query_num)
        if query_num == '0':
            df = pd.DataFrame(columns=['代码', '简称', '风险类型'])
            return df

        # 等待表格加载
        page.wait_for_selector(ROW_SELECTOR)

        # 获取表头
        table_headers = ["序号", "按钮", "股票代码", "股票简称"]
        header_elements = page.query_selector_all(HEADER_SELECTOR)

        pattern = r'\n\d{4}\.\d{2}\.\d{2}|\([^)]*\)|\[[^]]*\]'
        for header in header_elements:
            lines = header.inner_text().split("\n")
            if len(lines)>=3:
                # 提取公共部分和日期部分
                common_part = lines[0]
                for _ in lines[1:]:
                    table_headers.append(f"{common_part}")
            else:
                table_headers.append(re.sub(pattern,'',header.inner_text()).replace(" ",""))

        # 采集当前页数据
        all_data = []
        current_page = 1

        while True:
            print(f"正在采集第 {current_page} 页数据...")
            page_data = extract_data_fast(page)
            all_data.extend(page_data)
            print(f"第 {current_page} 页采集完成，已采集 {len(all_data)} 条数据")

            context_list = []
            # 检查是否有下一页
            li_elements = page.query_selector_all(DISABLED_SELECTOR)
            for i in li_elements:
                context_list.append(i.text_content())
            if_next_button = page.query_selector(DISABLED_SELECTOR)  # 使用 Playwright 特有的选择器
            if (if_next_button is not None and if_next_button.text_content() == '下页') or (
                    len(li_elements) == 2 and any("下页" in item for item in context_list)):
                print("已到达最后一页，采集结束。")
                break

            # 点击下一页
            next_button = page.query_selector(LAST_ITEM_SELECTOR)
            next_button.click()
            time.sleep(1)  # 防止请求过快
            page.wait_for_selector(ROW_SELECTOR)  # 等待新页面加载完成
            current_page += 1

        # 关闭浏览器
        browser.close()

        # 返回采集到的所有数据
        df = pd.DataFrame(all_data, columns=table_headers)[['股票代码','个股热度排名']]
        df['trade_date'] = now_str
        # print(df)
        return df


def popularity_query(now_str: str=None):
    table_name = f'popularity_day'  #_{now_year}
    query = f'主板，非st，{now_str}人气排名前200'
    save_popularity_mysql(query, now_str, table_name)

@db_retry(max_retries=5,initial_delay=1,max_delay=60,retriable_errors=(OperationalError, TimeoutError,AttributeError))
def save_popularity_mysql(query:str,now_str:str,table_name:str):
    try:
        df = wencai_query_popularity(query, now_str)
        unique_df = df.drop_duplicates()
    except TimeoutError:
        logger.error("表格未显示，数据类型：" + 'ztb')
        raise
    except Exception:
        # 捕获其他异常类型
        raise

    if unique_df.empty:
        logger.error("popularity_query》》》" + now_str + "》》》未获取值")
    else:
        if mysql_util.check_table_exists(table_name):
            mysql_util.delete_data(f"DELETE FROM `{table_name}` WHERE `trade_date`='{now_str}'")
        with engine.begin() as conn:
            unique_df.to_sql(name=table_name, con=conn, if_exists='append', index=False)
            print("表名：" + table_name + "、数量：" + str(unique_df.shape[0]))

def collect_base_query(start_date,end_date):
    # 问财基础数据
    base_query_day_sql = f"select trade_date from data_jyrl where  trade_date between '{start_date}' and '{end_date}' and trade_status='1' order by trade_date desc "
    base_query_day_df = pd.read_sql(base_query_day_sql, con=con)
    base_query_days = base_query_day_df.values.tolist()
    for day in base_query_days:
        set_date = day[0]
        base_query(set_date)

def collect_popularity_query(start_date,end_date):
    # 问财热股数据
    popularity_query_day_sql = f"select trade_date from data_jyrl where  trade_date between '{start_date}' and '{end_date}' and trade_status='1' order by trade_date desc "
    popularity_query_day_df = pd.read_sql(popularity_query_day_sql, con=con)
    popularity_query_days = popularity_query_day_df.values.tolist()
    for day in popularity_query_days:
        set_date = day[0]
        popularity_query(set_date)

def extract_data_fast(page):
    """优化的数据采集函数"""
    # 一次性获取所有行
    rows = page.locator(ROW_SELECTOR).all()
    data = []

    # 批量获取每行的单元格文本
    for row in rows:
        cells_text = row.locator('td').all_inner_texts()
        data.append(cells_text)

    return data


if __name__ == "__main__":
    start = time.time()

    deal_base_query_start_time = config_util.get_config("exe.history.wencai_collection.base_query.start_time")
    deal_base_query_end_time = config_util.get_config("exe.history.wencai_collection.base_query.end_time")

    deal_popularity_query_start_time = config_util.get_config("exe.history.wencai_collection.popularity_query.start_time")
    deal_popularity_query_end_time = config_util.get_config("exe.history.wencai_collection.popularity_query.end_time")

    collect_base_query(deal_base_query_start_time, deal_base_query_end_time)

    collect_popularity_query(deal_popularity_query_start_time, deal_popularity_query_end_time)

    con.close()

    end = time.time()
    execution_time = end - start
    logger.info(f"代码执行时间为: {execution_time} 秒")