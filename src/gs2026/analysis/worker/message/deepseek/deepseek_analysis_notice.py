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

# ── 拒绝检测与重试配置 ────────────────────────────────────────────────────────
MAX_RETRY_COUNT: int = 3  # 单条公告最大重试次数，达到后标记 skip

REFUSAL_PATTERNS: List[str] = [
    '我暂时无法回答',
    '让我们换个话题',
    '我无法处理',
    '无法为您提供',
    '我不能回答',
    '违反了我的使用政策',
    '不适合讨论',
    '无法协助',
    '抱歉，我不能',
    '作为AI助手',
    '作为一个AI',
]


def _is_refusal_response(text: str) -> bool:
    """检测 AI 是否返回了拒绝回答"""
    if not text or text.strip() in ('', '{}'):
        return False
    for pattern in REFUSAL_PATTERNS:
        if pattern in text:
            return True
    return False


def _get_current_fail_count(table_name: str, content_hash: str) -> int:
    """获取公告当前的失败次数"""
    try:
        safe_hash = content_hash.replace("'", "\\'")
        sql = f"SELECT analysis FROM {table_name} WHERE `内容hash`='{safe_hash}'"
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn)
        if df.empty:
            return 0
        val = df.iloc[0]['analysis']
        if val and str(val).startswith('fail_'):
            return int(str(val).split('_')[1])
        return 0
    except Exception:
        return 0


def _increment_fail_count(table_name: str, content_hash: str) -> None:
    """增加失败计数，达到阈值标记为 skip"""
    current = _get_current_fail_count(table_name, content_hash)
    safe_hash = content_hash.replace("'", "\\'")
    if current + 1 >= MAX_RETRY_COUNT:
        sql = f"UPDATE {table_name} SET analysis='skip' WHERE `内容hash`='{safe_hash}'"
        logger.warning(f"公告 {content_hash} 失败 {current + 1} 次，标记为 skip 永久跳过")
    else:
        sql = f"UPDATE {table_name} SET analysis='fail_{current + 1}' WHERE `内容hash`='{safe_hash}'"
        logger.info(f"公告 {content_hash} 失败计数: {current} -> {current + 1}")
    mysql_tool.update_data(sql)


def deepseek_ai(
    query_list: List[Tuple[str, str, Any, str]],
    notice_type_dic_str: str,
    table_name: str,
    analysis_table_name: str,
    _headless: bool,
    _is_retry: bool = False,  # 标记是否为重试调用，防止无限递归
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
        notice_yw: str = i[4]
        child_query: str = "公告id：" + content_hash + "，公告日期：" + notice_date + "，" + "股票代码：" + stock_code + "，标题为：" + title+"，公告原文："+notice_yw+" "
        query = query + child_query + "\n"

    # 拼接分析要求和JSON返回格式模板
    query = query + f"""
                    请以顶级短线游资的角度分析上述""" + str(count) + """条公告，逐一分析每条公告对次日股价的影响。返回结果为json结构并且能够直接复制，json 结构为
                
			        {"公告集合": [
                        {
                            "公告id": "",
                            "公告日期": "",
                            "股票代码": "",
                            "股票名称": "",
                            "公告标题": "",
                            "公告原文": "",
                            "核心内容": "",
                            "影响力度": "",
                            "消息类型": "",
                            "市场预期": "",
                            "开盘预判": "",
                            "持续性": "",
                            "判定依据": [""],
                            "关键要点": [""],
                            "隔夜策略": "",
                            "短线影响": "",
                            "中线影响": "",
                            "公告类型": ""
                        }
                    ]}
                
                    字段说明：
                    公告id：原样返回，只存一个id。
                    股票名称：根据股票代码查出对应A股最新名称。
                    公告原文：暂时为空。
					核心内容：用1-3句话总结：公告主体、时间、事件、关键数据、结论、直接后果。其中直接后果根据公告内容本身，推导该事项可能导致的结果，例如：资金被挪用 → 可能存在收回风险；业绩下修 → 净利润减少；合同中标 → 未来收入增加；不赎回可转债 → 债券继续存续，转股压力持续。只写公告里能直接推导出的后果，不写市场反应或概率预测。
                    
                    影响力度：该公告对股价的影响程度（不是风险高低）。
                      高 = 重大影响，足以单独驱动涨停/跌停（如业绩暴增超预期、重大重组、被ST等）
                      中 = 明显影响，可能带来2-5%波动（如中标大额合同、股东增减持、定增等）
                      低 = 轻微或无实质影响（如例行公告、日常关联交易、内控报告等）
                    
                    消息类型：该公告对股价的方向性判断。
                      利好 = 预期推动股价上涨
                      利空 = 预期导致股价下跌
                      中性 = 对股价无明显方向性影响
                    
                    【重要】影响力度与消息类型是两个独立维度：
                      影响力度=高 + 消息类型=利好 → 非常强的利好（如业绩暴增，次日大幅高开）
                      影响力度=高 + 消息类型=利空 → 非常强的利空（如业绩暴雷，次日大幅低开）
                      影响力度=低 + 消息类型=利好 → 轻微利好（影响有限）
                    
                    市场预期：该公告相对市场已有预期的位置。
                      超预期 = 显著好于/差于市场此前预期，会引发股价剧烈反应
                      符合预期 = 基本在市场预期范围内，可能已被price-in
                      低于预期 = 不及市场期望，虽然绝对值可能不差但相对预期偏弱
                    
                    开盘预判：基于公告内容预判次日开盘情况。
                      大幅高开(>5%) / 高开(2-5%) / 小幅高开(0-2%) / 平开 / 小幅低开(0-2%) / 低开(2-5%) / 大幅低开(>5%)
                    
                    持续性：该公告影响的时间跨度。
                      一日游 = 仅影响次日，之后回归常态
                      2-3日 = 短期内持续发酵
                      一周以上 = 中期影响，可能改变股票逻辑
                      持续发酵 = 长期利好/利空，基本面级别的变化
                    
                    判定依据：分析该公告影响力度和消息类型的核心理由，数组形式返回多条。
                    关键要点：公告的核心内容摘要，提炼最关键的信息点，数组形式返回。
                    隔夜策略：从隔夜超短视角给出具体操作建议，包括：
                      是否值得隔夜介入、预期收益空间、风险点、建议仓位。
                    
                    短线影响：该公告对1-3日短线交易的影响分析。
                    中线影响：该公告对1-4周中线持仓的影响分析。
                    公告类型:（公告类型字典：""" + notice_type_dic_str + """）
                    
                    结果返回能直接复制的完整的json数据。
            """
    # 对Prompt中的敏感词进行替换处理
    query = string_util.sensitive_word_replacement(query)

    # 调用DeepSeek模型进行分析
    analysis: str = deepseek_analysis_event_driven.deepseek_analysis(query, _headless)

    # ── 拒绝检测：如果 AI 拒绝回答，启动逐条重试 ─────────────────────────────
    if _is_refusal_response(analysis):
        logger.warning(f"DeepSeek 拒绝回答批次（{len(query_list)}条），原文: {analysis[:100]}...")
        logger.warning(f"启动逐条重试，涉及ID: {deal_id_list}")
        if not _is_retry:
            _retry_one_by_one(query_list, notice_type_dic_str, table_name, analysis_table_name, _headless)
        else:
            # 已经是重试调用，直接标记失败
            logger.warning(f"重试调用中仍被拒绝，标记所有公告失败: {deal_id_list}")
            for item in query_list:
                _increment_fail_count(table_name, item[0])
        return

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

            # 检查未被成功分析的公告（ID不在返回结果中），增加失败计数
            success_ids = set(ids)
            for item in query_list:
                if item[0] not in success_ids:
                    _increment_fail_count(table_name, item[0])
        else:
            logger.error(table_name + "该数据ai分析失败，启动逐条重试")
            logger.error(deal_id_list)
            if not _is_retry:
                _retry_one_by_one(query_list, notice_type_dic_str, table_name, analysis_table_name, _headless)
            else:
                logger.warning(f"重试调用中解析失败，标记所有公告失败: {deal_id_list}")
                for item in query_list:
                    _increment_fail_count(table_name, item[0])
            return

        logger.info(f"更新{table_name}表{len(ids)}条数据，更新id：{ids}")
    except JSONDecodeError:
        logger.error("json解析失败,JSONDecodeError，启动逐条重试")
        logger.error(deal_id_list)
        if not _is_retry:
            _retry_one_by_one(query_list, notice_type_dic_str, table_name, analysis_table_name, _headless)
        else:
            logger.warning(f"重试调用中JSON解析失败，标记所有公告失败: {deal_id_list}")
            for item in query_list:
                _increment_fail_count(table_name, item[0])
    except KeyError:
        logger.error("json解析失败,KeyError，启动逐条重试")
        logger.error(deal_id_list)
        if not _is_retry:
            _retry_one_by_one(query_list, notice_type_dic_str, table_name, analysis_table_name, _headless)
        else:
            logger.warning(f"重试调用中KeyError，标记所有公告失败: {deal_id_list}")
            for item in query_list:
                _increment_fail_count(table_name, item[0])

    end: float = time.time()
    execution_time: float = end - start
    logger.info(f"{table_name}AI分析耗时: {execution_time} 秒")


def _retry_one_by_one(
    query_list: List[Tuple[str, str, Any, str]],
    notice_type_dic_str: str,
    table_name: str,
    analysis_table_name: str,
    _headless: bool,
) -> None:
    """逐条重试失败的批次，遇到第一个失败立即停止。

    优化策略：逐条处理，成功则继续，遇到第一个失败立即停止，
    标记失败计数后退出，让主循环重新查询新批次。

    Args:
        query_list: 待重试公告列表，每个元素为 (内容hash, 公告标题, 公告日期, 股票代码)
        table_name: 数据源表名
        analysis_table_name: 分析结果表名
        _headless: 是否无头模式
    """
    logger.info(f"逐条重试开始，共 {len(query_list)} 条公告，遇到第一个失败立即停止")

    for item in query_list:
        content_hash = item[0]
        try:
            # 单条发送分析，传递 _is_retry=True 防止无限递归
            deepseek_ai([item], notice_type_dic_str, table_name, analysis_table_name, _headless, _is_retry=True)

            # 检查是否分析成功
            safe_hash = content_hash.replace("'", "\\'")
            check_sql = f"SELECT analysis FROM {table_name} WHERE `内容hash`='{safe_hash}'"
            with engine.connect() as conn:
                df = pd.read_sql(check_sql, conn)

            if not df.empty and df.iloc[0]['analysis'] == '1':
                # 成功，继续下一条
                logger.info(f"单条重试成功，继续下一条: {content_hash}")
            else:
                # 失败，标记并立即停止
                _increment_fail_count(table_name, content_hash)
                logger.warning(f"逐条重试遇到失败，立即停止: {content_hash}")
                break  # ❌ 立即停止，不再处理剩余消息

        except Exception as e:
            # 异常，标记并立即停止
            _increment_fail_count(table_name, content_hash)
            logger.error(f"单条重试异常，立即停止: {content_hash}, 错误: {e}")
            break  # ❌ 立即停止

        # 成功后的短暂延迟
        time.sleep(random.randint(2, 5))

    logger.info(f"逐条重试结束，重新查询新批次")


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
    # 查询未分析的公告记录（包含失败重试的），排除已跳过的，随机排序取前40条
    sql: str = f"select SQL_NO_CACHE `内容hash`,`公告标题`,`公告日期`,`代码`,`公告原文` from {table_name} where (analysis is null or analysis='' or analysis LIKE 'fail_%%') and content_status='1' order by rand() desc limit 40"
    # 【新增】公告类型字典查询
    notice_type_dic_sql: str = "select type from notice_type where flag='1'"
    try:
        with engine.connect() as conn:
            lists: List[List[Any]] = pd.read_sql(sql, con=conn).values.tolist()
            # 【新增】加载公告类型字典
            notice_type_dic_str: str = ','.join(pd.read_sql(notice_type_dic_sql, conn)['type'].astype(str))
            if 0 < len(lists) < 20:
                # 数据量较少时全量分析
                deepseek_ai(lists, notice_type_dic_str, table_name, analysis_table_name, _headless)
            if len(lists) >= 20:
                # 数据量较大时随机采样15-18条，控制单次Prompt长度
                sample_list: List[List[Any]] = random.sample(lists, random.randint(15, 18))
                deepseek_ai(sample_list, notice_type_dic_str, table_name, analysis_table_name, _headless)
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
