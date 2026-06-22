"""财联社新闻数据 AI 分析模块 —— DeepSeek 版本。

本模块负责从 MySQL 数据库中读取财联社（含第一财经、新华财网、人民财社）的
未分析新闻消息，构造 Prompt 交由 DeepSeek 大模型进行多维度评分与板块/概念
关联分析，并将分析结果回写数据库。

核心功能:
    - 批量拉取待分析新闻消息
    - 构造结构化 Prompt（包含评分维度、板块/概念字典）
    - 调用 DeepSeek 完成 AI 分析并解析 JSON 结果
    - 事务性地将分析结果写入分析表、标记原始消息为已分析
    - 以轮询方式持续运行，支持后台守护线程

依赖:
    - gs2026.utils: mysql_util, config_util, email_util, log_util, string_util 等工具模块
    - gs2026.analysis.worker.message.deepseek.deepseek_analysis_event_driven: DeepSeek 分析入口
    - SQLAlchemy / pandas: 数据库访问与数据处理
"""

import json
import random
import time
import warnings
from datetime import datetime
from json.decoder import JSONDecodeError
from pathlib import Path
from typing import Any, List

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning

from gs2026.utils import mysql_util, config_util, pandas_display_config
from gs2026.utils import log_util, string_util
from gs2026.utils.task_runner import run_daemon_task
from gs2026.utils.distributed_lock import DistributedLockManager
from gs2026.analysis.worker.message.deepseek import deepseek_analysis_event_driven
from gs2026.analysis.worker.message.prompts import build_news_cls_prompt

# 忽略 SQLAlchemy 的弃用警告，避免日志噪音
warnings.filterwarnings("ignore", category=SAWarning)

# ── 模块级初始化 ──────────────────────────────────────────────────────────────
logger = log_util.setup_logger(str(Path(__file__).absolute()))
pandas_display_config.set_pandas_display_options()

# 数据库连接配置
url: str = config_util.get_config('common.url')
deepseek_corpus_version_cls: str = config_util.get_config('common.deepseek_corpus_version.cls')

engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
mysql_tool = mysql_util.get_mysql_tool(url)

# Redis 客户端（用于分布式锁）
import redis
redis_host: str = config_util.get_config('common.redis.host')
redis_port: int = config_util.get_int('common.redis.port')
redis_client: redis.Redis = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)

# 浏览器页面超时时间（毫秒）
page_timeout: int = 360000

# ── 拒绝检测与重试配置 ────────────────────────────────────────────────────────
MAX_RETRY_COUNT: int = 3  # 单条消息最大重试次数，达到后标记 skip

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
    """获取消息当前的失败次数"""
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
        logger.warning(f"消息 {content_hash} 失败 {current + 1} 次，标记为 skip 永久跳过")
    else:
        sql = f"UPDATE {table_name} SET analysis='fail_{current + 1}' WHERE `内容hash`='{safe_hash}'"
        logger.info(f"消息 {content_hash} 失败计数: {current} -> {current + 1}")
    mysql_tool.update_data(sql)


def deepseek_ai(
    query_list: List[List[Any]],
    bk_dic_str: str,
    gn_dic_str: str,
    table_name: str,
    analysis_table_name: str,
    _headless: bool,
    _is_retry: bool = False,  # 标记是否为重试调用，防止无限递归
) -> None:
    """调用 DeepSeek 大模型对一批新闻消息进行多维度 AI 分析。

    将消息列表拼装为结构化 Prompt，经过敏感词替换后发送给 DeepSeek，
    解析返回的 JSON 结果并以事务方式写入数据库。

    Args:
        query_list: 待分析消息列表，每个元素为 [内容hash, 内容] 的子列表。
        bk_dic_str: 板块名称字典字符串（逗号分隔），用于 Prompt 中约束板块范围。
        gn_dic_str: 概念名称字典字符串（逗号分隔），用于 Prompt 中约束概念范围。
        table_name: 源数据表名（如 ``news_cls2026``）。
        analysis_table_name: 分析结果写入的目标表名（如 ``analysis_news2026``）。
        _headless: 是否以无头模式运行浏览器。

    Raises:
        JSONDecodeError: AI 返回内容无法解析为合法 JSON 时记录错误日志。
        KeyError: JSON 结构缺少预期字段时记录错误日志。

    """

    start: float = time.time()
    update_time: str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    query: str = ""
    count: int = len(query_list)
    # 提取所有待处理消息的 hash ID，用于异常时日志输出
    deal_id_list: List[str] = [row[0] for row in query_list]

    # ── 拼装消息文本 ──────────────────────────────────────────────────────────
    for i in query_list:
        content_hash: str = i[0]
        content: str = i[1]
        child_query: str = "消息id：" + content_hash + ",消息内容：" + content
        query = query + child_query + "\n"

    # ── 构造完整 Prompt（使用 prompts.py 的 build_news_cls_prompt） ─────────────────────────────
    query = build_news_cls_prompt(query, count, bk_dic_str, gn_dic_str)
    print(query)
    # 对 Prompt 进行敏感词替换，避免触发模型安全策略
    query = string_util.sensitive_word_replacement(query)
    # 调用 DeepSeek 大模型执行分析
    analysis: str = deepseek_analysis_event_driven.deepseek_analysis(query, _headless)

    # ── 拒绝检测：如果 AI 拒绝回答，启动逐条重试 ─────────────────────────────
    if _is_refusal_response(analysis):
        logger.warning(f"DeepSeek 拒绝回答批次（{len(query_list)}条），原文: {analysis[:100]}...")
        logger.warning(f"启动逐条重试，涉及ID: {deal_id_list}")
        if not _is_retry:
            _retry_one_by_one(query_list, bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
        else:
            # 已经是重试调用，直接标记失败
            logger.warning(f"重试调用中仍被拒绝，标记所有消息失败: {deal_id_list}")
            for item in query_list:
                _increment_fail_count(table_name, item[0])
        return

    # ── 清洗 AI 返回文本，提取有效 JSON ──────────────────────────────────────
    analysis = string_util.remove_json_prefix(analysis, 'json')
    analysis = string_util.remove_json_prefix(analysis, 'Copy')
    analysis = string_util.remove_json_prefix(analysis, 'Code')
    analysis = string_util.remove_json_comments(analysis)
    analysis = analysis.lstrip()
    json_data, remaining_text = string_util.extract_json_from_string(analysis)

    # ── 解析 JSON 并写入数据库 ────────────────────────────────────────────────
    try:
        analysis_json: dict = json.loads(json_data)
        ids: List[str] = string_util.extract_message_ids(analysis_json, "消息集合", "消息id")
        ids_count: int = len(ids)

        # 仅当解析出有效消息 ID 且 JSON 合法非空时才执行数据库写入
        if ids_count > 0 and string_util.is_valid_json(json_data) and json_data.strip() != '{}' and json_data != '':
            ids_str: str = "(" + ",".join(f"'{item}'" for item in ids) + ")"
            # ① 标记原始表已分析
            update_sql1: str = f"UPDATE {table_name} SET analysis='1' WHERE `内容hash` in {ids_str}"
            # ② 兼容：保留原始 JSON 写入旧表（过渡期）
            update_sql2: str = f"INSERT INTO  {analysis_table_name} (table_name,json_value,update_time,version) VALUES  ('{table_name}','{json_data}','{update_time}','{deepseek_corpus_version_cls}') "
            mysql_tool.update_transactions_data(update_sql1, update_sql2)

            # ③ 新增：拆分入库 + 写 Redis 缓存
            try:
                from gs2026.analysis.worker.message.deepseek.processor.news import process_batch
                batch_stats = process_batch(json_data, table_name, deepseek_corpus_version_cls)
                logger.info(f"拆分入库完成: {batch_stats}")
            except Exception as proc_err:
                logger.error(f"拆分入库异常（不影响主流程）: {proc_err}")

            # ④ 检查未被成功分析的消息（ID不在返回结果中），增加失败计数
            success_ids = set(ids)
            for item in query_list:
                if item[0] not in success_ids:
                    _increment_fail_count(table_name, item[0])
        else:
            logger.error(table_name + "该数据ai分析失败，启动逐条重试")
            logger.error(deal_id_list)
            if not _is_retry:
                _retry_one_by_one(query_list, bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
            else:
                logger.warning(f"重试调用中解析失败，标记所有消息失败: {deal_id_list}")
                for item in query_list:
                    _increment_fail_count(table_name, item[0])
            return

        logger.info(f"更新{table_name}表{len(ids)}条数据，更新id：{ids}")
    except JSONDecodeError:
        logger.error("json解析失败,JSONDecodeError，启动逐条重试")
        logger.error(deal_id_list)
        if not _is_retry:
            _retry_one_by_one(query_list, bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
        else:
            logger.warning(f"重试调用中JSON解析失败，标记所有消息失败: {deal_id_list}")
            for item in query_list:
                _increment_fail_count(table_name, item[0])
    except KeyError:
        logger.error("json解析失败,KeyError，启动逐条重试")
        logger.error(deal_id_list)
        if not _is_retry:
            _retry_one_by_one(query_list, bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
        else:
            logger.warning(f"重试调用中KeyError，标记所有消息失败: {deal_id_list}")
            for item in query_list:
                _increment_fail_count(table_name, item[0])

    end: float = time.time()
    execution_time: float = end - start
    logger.info(f"{table_name}AI分析耗时: {execution_time} 秒")


def _retry_one_by_one(
    query_list: List[List[Any]],
    bk_dic_str: str,
    gn_dic_str: str,
    table_name: str,
    analysis_table_name: str,
    _headless: bool,
) -> None:
    """逐条重试失败的批次，遇到第一个失败立即停止。

    优化策略：逐条处理，成功则继续，遇到第一个失败立即停止，
    标记失败计数后退出，让主循环重新查询新批次。

    Args:
        query_list: 待重试消息列表，每个元素为 [内容hash, 内容]
        其余参数同 deepseek_ai
    """
    logger.info(f"逐条重试开始，共 {len(query_list)} 条消息，遇到第一个失败立即停止")

    for item in query_list:
        content_hash = item[0]
        try:
            # 单条发送分析，传递 _is_retry=True 防止无限递归
            deepseek_ai([item], bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless, _is_retry=True)

            # 检查是否分析成功（analysis='1'）
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


def get_news_cls_analysis(
    table_name: str,
    analysis_table_name: str,
    _headless: bool,
) -> None:
    """从数据库拉取待分析的财联社新闻并交由 AI 分析（使用通用分布式锁）。

    Args:
        table_name: 源数据表名。
        analysis_table_name: 分析结果目标表名。
        _headless: 是否以无头模式运行浏览器。
    """
    # 查询未分析的消息（包含失败重试的），排除已跳过的，按发布时间降序并随机排列，限制 60 条
    sql: str = (f"select SQL_NO_CACHE `内容hash`,`内容` from {table_name} "
                f"where (analysis is null or analysis='' or analysis LIKE 'fail_%%') "
                f"order by SUBSTRINg(`发布时间`,1,7) desc,rand() limit 60")
    bk_dic_sql: str = "select name from data_industry_code_ths"
    gn_dic_sql: str = "select name from ths_gn_names_rq where flag='1'"

    with engine.connect() as conn:
        lists: List[List[Any]] = pd.read_sql(sql, con=conn).values.tolist()
        # 加载板块和概念字典，用于 Prompt 约束
        bk_dic_str: str = ','.join(pd.read_sql(bk_dic_sql, conn)['name'].astype(str))
        gn_dic_str: str = ','.join(pd.read_sql(gn_dic_sql, conn)['name'].astype(str))

        if len(lists) < 30:
            # 数据量过少，暂不处理，等待更多数据积累
            logger.info("当前数据量小于30。暂不处理")
            time.sleep(600)
            return
        
        # 【新增】使用通用分布式锁管理器
        lock_mgr = DistributedLockManager(redis_client, lock_timeout=900)
        
        # 1. 过滤掉已被锁定的消息
        available = lock_mgr.filter_locked(
            lists,
            key_func=lambda item: f"news_ai_lock:{table_name}:{item[0]}"
        )
        
        if len(available) < 30:
            logger.info(f"可用消息（未锁定）{len(available)}条，小于30，休眠等待")
            time.sleep(60)
            return
        
        # 2. 从可用消息中采样
        sample_list = random.sample(available, random.randint(15, 18))
        
        # 3. 批量加锁
        locked = lock_mgr.batch_try_lock(
            sample_list,
            key_func=lambda item: f"news_ai_lock:{table_name}:{item[0]}"
        )
        
        if len(locked) < 5:
            logger.info(f"成功加锁消息{len(locked)}条，过少，释放锁后休眠")
            lock_mgr.release_all()
            time.sleep(60)
            return
        
        logger.info(f"采样{len(sample_list)}条，成功加锁{len(locked)}条，开始分析")
        
        # 4. 分析（确保锁释放）
        try:
            items_to_analyze = [item for item, _ in locked]
            deepseek_ai(items_to_analyze, bk_dic_str, gn_dic_str, 
                       table_name, analysis_table_name, _headless)
        finally:
            lock_mgr.release_all()


def time_task_do_cls(polling_time: int, year: str = "2026") -> None:
    """定时轮询任务：持续对财联社新闻执行 AI 分析。

    以 ``polling_time`` 秒为间隔循环调用分析流程。

    Args:
        polling_time: 每轮分析后的休眠时间（秒）。
        year: 年份，用于构造表名，默认"2026"。
    """
    while True:
        get_news_cls_analysis("news_cls" + year, "analysis_news" + year, True)
        time.sleep(polling_time)


if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description='财联社数据分析')
    parser.add_argument('--params', type=str, help='JSON格式的参数') 
    args = parser.parse_args()
    
    # 默认年份
    year = "2026"
    
    # 解析命令行参数
    if args.params:
        try:
            params = json.loads(args.params)
            if 'year' in params:
                year = params['year']
                logger.info(f'从参数获取年份: {year}')
        except json.JSONDecodeError as e:
            logger.error(f'参数解析失败: {e}')
    
    run_daemon_task(target=time_task_do_cls, args=(10, year))
