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
from gs2026.analysis.worker.message.deepseek.result_processor import process_notice
from gs2026.utils.task_runner import run_daemon_task

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
mysql_tool = mysql_util.get_mysql_tool(url)
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
					        "股票名称": "",
					        "公告标题": "",
					        "风险大小": "",
					        "消息类型": "",
					        "判定依据":[""],
					        "关键要点":[""],
					        "短线影响": "",
					        "中线影响": ""
                        }   
					]}
                
                    其中，公告id字段只存一个id
                    股票名称根据股票代码查询得到
                    风险大小字典值有高，中，低三个。
                    消息类型的字典值有利好，利空，中性三个。
                    判定依据是分析该公告为利好或利空的依据，用数组形式返回多条依据
                    关键要点是公告的核心内容摘要，用数组形式返回多条要点
                    短线影响是该公告对短线交易的影响描述
                    中线影响是该公告对中线持仓的影响描述
                    
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
            mysql_tool.update_transactions_data(update_sql1, update_sql2)
            
            # 拆分入库到新表（analysis_notice_detail_2026）
            try:
                stats = process_notice(analysis, version=deepseek_corpus_version_notice)
                logger.info(f"公告分析拆分入库: {stats}")
            except Exception as e:
                logger.error(f"公告分析拆分入库失败: {e}")

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


def timer_task_do_notice(polling_time: int, year: str = "2026") -> None:
    """持续轮询执行公告AI分析任务。

    循环调用get_notice_analysis查询并分析未处理的公告数据，
    直到所有数据分析完毕。每轮分析后休眠指定秒数。

    Args:
        polling_time: 每轮分析后的休眠时间（秒）。
        year: 年份，用于拼接表名，默认"2026"。

    """
    while True:
        # 使用传入的year参数拼接表名
        flag = get_notice_analysis(f"jhsaggg{year}", f"analysis_notices{year}", True)
        if not flag:
            # 无数据时退出循环（所有数据已分析完成）
            logger.info(f"公告分析完成，年份: {year}")
            break
        time.sleep(polling_time)


if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description='公告分析')
    parser.add_argument('--params', type=str, help='JSON格式的参数')
    args = parser.parse_args()
    
    # 默认参数
    year = "2026"
    polling_time = 1
    
    # 解析命令行参数
    if args.params:
        try:
            params = json.loads(args.params)
            if 'year' in params:
                year = params['year']
                logger.info(f'从参数获取年份: {year}')
            if 'polling_time' in params:
                polling_time = int(params['polling_time'])
                logger.info(f'从参数获取轮询时间: {polling_time}')
        except json.JSONDecodeError as e:
            logger.error(f'参数解析失败: {e}')
    
    run_daemon_task(target=timer_task_do_notice, args=(polling_time, year), daemon=False)
