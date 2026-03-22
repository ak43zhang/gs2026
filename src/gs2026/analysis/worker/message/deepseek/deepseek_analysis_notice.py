"""公告数据AI分析模块 - DeepSeek版本。

本模块负责对上市公司公告数据进行AI智能分析，通过DeepSeek大模型
从短线游资视角判定公告的风险大小、消息类型（利好/利空/中性）及判定依据。

核心功能:
    - 批量构建公告分析Prompt，调用DeepSeek模型进行智能研判
    - 解析AI返回的JSON结果并以事务方式持久化到数据库
    - 支持随机采样和轮询机制，持续处理未分析的公告数据
    - 异常时自动发送邮件告警

依赖关系:
    - gs2026.utils: MySQL工具、配置管理、邮件工具、日志工具等
    - gs2026.analysis.worker.message.deepseek.deepseek_analysis_event_driven: DeepSeek分析引擎
    - pandas / sqlalchemy: 数据读取与数据库连接

Typical usage:
    >>> timer_task_do_notice(1)
"""
import json
import os
import random
import time
import warnings
from datetime import datetime
from json.decoder import JSONDecodeError
from pathlib import Path
from typing import List, Tuple, Any, Optional

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning

from gs2026.utils import (mysql_util,
                          config_util,
                          email_util,
                          pandas_display_config,
                          log_util,
                          string_enum,
                          string_util)
from gs2026.analysis.worker.message.deepseek import deepseek_analysis_event_driven

# 忽略SQLAlchemy的SAWarning警告，避免日志干扰
warnings.filterwarnings("ignore", category=SAWarning)

# 初始化日志记录器，使用当前文件的绝对路径作为logger名称
logger = log_util.setup_logger(str(Path(__file__).absolute()))
# 设置pandas的全局显示选项
pandas_display_config.set_pandas_display_options()

# 从配置文件读取数据库连接URL和公告分析语料版本号
url: str = config_util.get_config("common.url")
deepseek_corpus_version_notice: str = config_util.get_config('common.deepseek_corpus_version.notice')

# 创建SQLAlchemy数据库引擎，启用连接池回收和预检测
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()
# Firefox浏览器路径（用于无头浏览器场景）
browser_path: str = string_enum.FIREFOX_PATH_1509
# 初始化MySQL工具和邮件工具实例
mysql_util = mysql_util.MysqlTool(url)
email_util = email_util.EmailUtil()

# 页面加载超时时间（毫秒）
page_timeout: int = 360000


def deepseek_ai(
    query_list: List[Tuple[str, str, Any, str]],
    table_name: str,
    analysis_table_name: str,
    _headless: bool
) -> None:
    """调用DeepSeek AI对公告数据进行批量分析。

    将多条公告拼接成一个Prompt，调用DeepSeek模型从短线游资视角
    分析每条公告的风险大小、消息类型和判定依据，解析JSON结果后
    以数据库事务方式同步更新数据源表和分析结果表。

    Args:
        query_list: 待分析的公告列表，每个元素为
            (内容hash, 公告标题, 公告日期, 股票代码) 的元组。
        table_name: 公告数据源表名。
        analysis_table_name: 分析结果存储表名。
        _headless: 是否使用无头浏览器模式运行DeepSeek。

    Raises:
        JSONDecodeError: AI返回的结果无法解析为合法JSON时捕获并记录日志。
        KeyError: JSON结构中缺少预期字段时捕获并记录日志。

    Example:
        >>> query_list = [('hash123', '关于重大资产重组的公告', '2025-03-20', '600519')]
        >>> deepseek_ai(query_list, 'jhsaggg2025', 'analysis_notices2025', True)
    """
    update_time: str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    start: float = time.time()
    query: str = ""
    count: int = len(query_list)
    # 提取所有待处理的公告ID列表，用于异常日志追踪
    deal_id_list: List[str] = [row[0] for row in query_list]

    # 逐条拼接公告信息到Prompt中
    for i in query_list:
        content_hash: str = i[0]
        title: str = i[1]
        notice_date: str = str(i[2])
        stock_code: str = i[3]
        child_query: str = "公告id：" + content_hash + "，公告日期：" + notice_date + "，" + "股票代码：" + stock_code + "，标题为：" + title
        query = query + child_query + "\n"

    # 拼接分析要求和JSON返回格式模板
    query = query + f"""
                    请以顶级短线游资的角度分析上述""" + str(count) + """条公告进行逐一分析，返回结果为json结构并且能够直接复制，json 结构为
                
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
                    
                    结果返回能直接复制的完整的json数据。
            """
    # 对Prompt中的敏感词进行替换处理
    query = string_util.sensitive_word_replacement(query)

    # 调用DeepSeek模型进行分析
    analysis: str = deepseek_analysis_event_driven.deepseek_analysis(query, _headless)

    # 解析AI返回的JSON字符串并持久化分析结果
    try:
        analysis_json: dict = json.loads(analysis)
        # 从JSON结果中提取所有公告ID
        ids: List[str] = string_util.extract_message_ids(analysis_json, "公告集合", "公告id")
        ids_count: int = len(ids)
        if ids_count > 0 and string_util.is_valid_json(analysis) and analysis.strip() != '{}' and analysis != '':
            # 构建IN子句，用于批量更新数据源表的分析状态
            ids_str: str = "(" + ",".join(f"'{item}'" for item in ids) + ")"
            update_sql1: str = f"UPDATE {table_name} SET analysis='1' WHERE `内容hash` in {ids_str}"
            update_sql2: str = f"INSERT INTO  {analysis_table_name} (table_name,json_value,update_time,version) VALUES  ('{table_name}','{analysis}','{update_time}','{deepseek_corpus_version_notice}') "
            # 以事务方式同步执行两条SQL，保证数据一致性
            mysql_util.update_transactions_data(update_sql1, update_sql2)

        else:
            logger.error(table_name + "该数据ai分析失败，请重试")
            logger.error(deal_id_list)

        logger.info(f"更新{table_name}表{len(ids)}条数据，更新id：{ids}")
    except JSONDecodeError:
        logger.error("json解析失败,JSONDecodeError")
        logger.error(deal_id_list)
    except KeyError:
        logger.error("json解析失败,KeyError")
        logger.error(deal_id_list)

    end: float = time.time()
    execution_time: float = end - start
    logger.info(f"{table_name}AI分析耗时: {execution_time} 秒")


def wait_for_any_selector_simple(
    page: Any,
    selectors: List[str],
    timeout: int = 3000
) -> str:
    """轮询检测页面中多个CSS选择器，返回第一个匹配的选择器。

    在指定超时时间内以200ms间隔轮询检测多个选择器，
    返回第一个在页面中存在的选择器字符串。

    Args:
        page: Playwright页面对象。
        selectors: 待检测的CSS选择器列表。
        timeout: 超时时间（毫秒），默认3000ms。

    Returns:
        str: 第一个在页面中匹配到的CSS选择器字符串。

    Raises:
        TimeoutError: 在超时时间内未找到任何匹配的选择器。

    Example:
        >>> selector = wait_for_any_selector_simple(page, ['.result', '.error'], timeout=5000)
    """
    start_time: float = time.time()
    while time.time() - start_time < timeout:
        for selector in selectors:
            element = page.query_selector(selector)
            if element:
                return selector
        # 短暂等待后继续轮询，避免CPU空转
        page.wait_for_timeout(200)
    raise TimeoutError(f"在 {timeout}ms 内未找到任何选择器: {selectors}")


def get_notice_analysis(
    table_name: str,
    analysis_table_name: str,
    _headless: bool
) -> bool:
    """查询未分析的公告数据并触发AI分析。

    从数据源表中查询未完成AI分析的公告记录，根据数量决定
    是全量分析还是随机采样分析，调用deepseek_ai进行处理。

    Args:
        table_name: 公告数据源表名。
        analysis_table_name: 分析结果存储表名。
        _headless: 是否使用无头浏览器模式。

    Returns:
        bool: 如果存在待分析数据并已触发分析返回True，否则返回False。

    Example:
        >>> flag = get_notice_analysis('jhsaggg2026', 'analysis_notices2026', True)
    """
    flag: bool = True
    # 查询未分析的公告记录，随机排序取前40条
    sql: str = f"select SQL_NO_CACHE `内容hash`,`公告标题`,`公告日期`,`代码` from {table_name} where analysis is null or analysis='' order by rand() desc limit 40"
    try:
        with engine.connect() as conn:
            lists: List[List[Any]] = pd.read_sql(sql, con=conn).values.tolist()
            if 0 < len(lists) < 20:
                # 数据量较少时全量分析
                deepseek_ai(lists, table_name, analysis_table_name, _headless)
            if len(lists) >= 20:
                # 数据量较大时随机采样15-18条，控制单次Prompt长度
                sample_list: List[List[Any]] = random.sample(lists, random.randint(15, 18))
                deepseek_ai(sample_list, table_name, analysis_table_name, _headless)
            else:
                # 无待分析数据，返回False终止轮询
                flag = False
    finally:
        if conn is not None:
            conn.close()
    return flag


def timer_task_do_notice(polling_time: int) -> None:
    """持续轮询执行公告AI分析任务。

    循环调用get_notice_analysis查询并分析未处理的公告数据，
    直到所有数据分析完毕。每轮分析后休眠指定秒数。

    Args:
        polling_time: 每轮分析后的休眠时间（秒）。

    Example:
        >>> timer_task_do_notice(1)
    """
    flag: bool = True
    while flag:
        # 指定目标年份，用于拼接数据源表名和分析结果表名
        year: str = '2026'
        flag = get_notice_analysis("jhsaggg" + year, "analysis_notices" + year, True)
        time.sleep(polling_time)


if __name__ == "__main__":
    start_deal_time: float = time.time()
    file_name: str = os.path.basename(__file__)

    # 主线程保持运行，执行公告分析轮询任务
    try:
        timer_task_do_notice(1)
    except Exception as e:
        logger.exception(f"采集流程失败: {e}")
        # 构建异常告警邮件并发送给所有配置的接收人
        ERROR_TITLE = "异常告警"
        ERROR_CONTENT = f"{file_name} 执行异常: {str(e)}"
        FULL_HTML = email_util.full_html_fun(ERROR_TITLE, ERROR_CONTENT)
        for receiver_email in email_util.get_email_list():
            email_util.email_send_html(receiver_email, "异常告警", FULL_HTML)
        raise
    finally:
        # 确保数据库事务提交并关闭连接
        con.commit()
        con.close()

    end_deal_time: float = time.time()
    total_execution_time: float = end_deal_time - start_deal_time
    logger.info(f"----------AI分析总耗时: {total_execution_time} 秒-----------")
