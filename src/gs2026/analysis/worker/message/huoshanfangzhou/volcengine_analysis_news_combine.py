"""综合财经新闻数据 AI 分析模块 —— 火山方舟版本。

完全对齐 DeepSeek 版逻辑，仅替换 AI 调用层：
  - 不调用浏览器，走火山方舟 HTTP API
  - 删除敏感词替换
  - 删除 JSON 清理（直接 json.loads）
  - 其余逻辑（拒绝检测、失败计数、逐条重试、入库）完全一致

与 cls 版区别：
  - 数据源为 news_combine 表（多平台聚合）
  - 综合评分公式：重要程度评分×5（cls 版本为 ×4）
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

from gs2026.utils import mysql_util, config_util, email_util, pandas_display_config
from gs2026.utils import log_util, string_enum, string_util
from gs2026.utils.task_runner import run_daemon_task
from gs2026.analysis.worker.message.prompts import build_news_cls_prompt
from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_client import (
    volcengine_analysis,
)

warnings.filterwarnings("ignore", category=SAWarning)

# ── 模块级初始化 ──────────────────────────────────────────────────────────────
logger = log_util.setup_logger(str(Path(__file__).absolute()))
pandas_display_config.set_pandas_display_options()

url: str = config_util.get_config("common.url")
deepseek_corpus_version_combine: str = config_util.get_config('common.deepseek_corpus_version.combine')

engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
mysql_tool = mysql_util.get_mysql_tool(url)
email_util_inst = email_util.EmailUtil()

# ── 拒绝检测与重试配置 ────────────────────────────────────────────────────────
MAX_RETRY_COUNT: int = 3

REFUSAL_PATTERNS: List[str] = [
    '我暂时无法回答', '让我们换个话题', '我无法处理', '无法为您提供',
    '我不能回答', '违反了我的使用政策', '不适合讨论', '无法协助',
    '抱歉，我不能', '作为AI助手', '作为一个AI',
]


def _is_refusal_response(text: str) -> bool:
    if not text or text.strip() in ('', '{}'):
        return False
    for pattern in REFUSAL_PATTERNS:
        if pattern in text:
            return True
    return False


def _get_current_fail_count(table_name: str, content_hash: str) -> int:
    try:
        safe_hash = content_hash.replace("'", "\\'")
        sql = f"SELECT analysis FROM {table_name} WHERE `内容hash`='{safe_hash}'"
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn)
            df = df.copy()  # 复制数据避免与连接关联
        if df.empty:
            return 0
        val = df.iloc[0]['analysis']
        if val and str(val).startswith('fail_'):
            return int(str(val).split('_')[1])
        return 0
    except Exception:
        return 0


def _increment_fail_count(table_name: str, content_hash: str) -> None:
    current = _get_current_fail_count(table_name, content_hash)
    safe_hash = content_hash.replace("'", "\\'")
    if current + 1 >= MAX_RETRY_COUNT:
        sql = f"UPDATE {table_name} SET analysis='skip' WHERE `内容hash`='{safe_hash}'"
        logger.warning(f"消息 {content_hash} 失败 {current + 1} 次，标记为 skip")
    else:
        sql = f"UPDATE {table_name} SET analysis='fail_{current + 1}' WHERE `内容hash`='{safe_hash}'"
        logger.info(f"消息 {content_hash} 失败计数: {current} -> {current + 1}")
    mysql_tool.update_data(sql)


def volcengine_ai(
    query_list: List[List[Any]],
    bk_dic_str: str,
    gn_dic_str: str,
    table_name: str,
    analysis_table_name: str,
    _headless: bool = True,
    _is_retry: bool = False,
) -> None:
    """火山方舟AI分析主函数（接口与 deepseek_ai 完全一致）"""
    start = time.time()
    update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    count = len(query_list)
    deal_id_list = [row[0] for row in query_list]

    # ── 拼装消息文本 ──────────────────────────────────────────────────────────
    query = ""
    for i in query_list:
        content_hash = i[0]
        content = i[1]
        child_query = f"消息id：{content_hash},消息内容：{content}"
        query = query + child_query + "\n"

    # ── 构造完整 Prompt（使用 prompts.py 的 build_news_cls_prompt） ─────────────────────
    query = build_news_cls_prompt(query, count, bk_dic_str, gn_dic_str)
    # print(query)  # 如需调试可取消注释

    # 调用火山方舟API获取AI分析结果
    logger.info(f"[火山方舟-聚合] 开始分析: {count}条消息, IDs: {deal_id_list}")
    try:
        analysis: str = volcengine_analysis(query)
    except Exception as e:
        logger.error(f"[火山方舟-聚合] API调用异常: {e}")
        for item in query_list:
            _increment_fail_count(table_name, item[0])
        return

    # ── 拒绝检测 ─────────────────────────────────────────────────────────────
    if _is_refusal_response(analysis):
        logger.warning(f"[火山方舟-聚合] 拒绝回答批次（{count}条），原文: {analysis[:100]}...")
        if not _is_retry:
            _retry_one_by_one(query_list, bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
        else:
            logger.warning(f"[火山方舟-聚合] 重试中仍被拒绝，标记失败: {deal_id_list}")
            for item in query_list:
                _increment_fail_count(table_name, item[0])
        return

    if not analysis or analysis.strip() in ('', '{}'):
        logger.error(f"[火山方舟-聚合] 返回空结果，启动逐条重试")
        if not _is_retry:
            _retry_one_by_one(query_list, bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
        else:
            for item in query_list:
                _increment_fail_count(table_name, item[0])
        return

    # ── 解析 JSON 并写入数据库 ────────────────────────────────────────────────
    try:
        from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_client import repair_llm_json, save_json_error
        json_data = repair_llm_json(analysis.strip())
        analysis_json: dict = json.loads(json_data)
        ids: List[str] = string_util.extract_message_ids(analysis_json, "消息集合", "消息id")
        ids_count = len(ids)

        if ids_count > 0 and json_data and json_data != '{}':
            ids_str = "(" + ",".join(f"'{item}'" for item in ids) + ")"
            # ① 标记原始表已分析
            update_sql1 = f"UPDATE {table_name} SET analysis='1' WHERE `内容hash` in {ids_str}"
            # ② 兼容：写入旧表
            update_sql2 = (
                f"INSERT INTO {analysis_table_name} "
                f"(table_name,json_value,update_time,version) VALUES "
                f"('{table_name}','{json_data}','{update_time}','{deepseek_corpus_version_combine}')"
            )
            mysql_tool.update_transactions_data(update_sql1, update_sql2)

            # ③ 拆分入库 + 写 Redis 缓存
            try:
                from gs2026.analysis.worker.message.deepseek.processor.news import process_batch
                batch_stats = process_batch(json_data, table_name, deepseek_corpus_version_combine)
                logger.info(f"[火山方舟-聚合] 拆分入库完成: {batch_stats}")
            except Exception as proc_err:
                logger.error(f"[火山方舟-聚合] 拆分入库异常: {proc_err}")

            # ④ 未被成功分析的消息，增加失败计数
            success_ids = set(ids)
            for item in query_list:
                if item[0] not in success_ids:
                    _increment_fail_count(table_name, item[0])
        else:
            logger.error(f"[火山方舟-聚合] 未解析到有效消息ID，启动逐条重试")
            if not _is_retry:
                _retry_one_by_one(query_list, bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
            else:
                for item in query_list:
                    _increment_fail_count(table_name, item[0])

        logger.info(f"[火山方舟-聚合] 更新{table_name}表{ids_count}条数据")
    except JSONDecodeError as e:
        save_json_error('volcengine_news_combine', analysis.strip(), str(e))
        logger.error(f"[火山方舟-聚合] JSON解析失败,JSONDecodeError（已保存），启动逐条重试")
        logger.error(deal_id_list)
        if not _is_retry:
            _retry_one_by_one(query_list, bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
        else:
            for item in query_list:
                _increment_fail_count(table_name, item[0])
    except KeyError:
        logger.error(f"[火山方舟-聚合] JSON解析失败,KeyError，启动逐条重试")
        logger.error(deal_id_list)
        if not _is_retry:
            _retry_one_by_one(query_list, bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
        else:
            for item in query_list:
                _increment_fail_count(table_name, item[0])

    elapsed = time.time() - start
    logger.info(f"[火山方舟-聚合] {table_name}分析完成，耗时: {elapsed:.2f}秒")


def _retry_one_by_one(
    query_list: List[List[Any]],
    bk_dic_str: str,
    gn_dic_str: str,
    table_name: str,
    analysis_table_name: str,
    _headless: bool,
) -> None:
    """逐条重试，遇到第一个失败立即停止"""
    logger.info(f"[火山方舟-聚合] 逐条重试开始，共 {len(query_list)} 条")

    for item in query_list:
        content_hash = item[0]
        try:
            volcengine_ai([item], bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless, _is_retry=True)

            safe_hash = content_hash.replace("'", "\\'")
            check_sql = f"SELECT analysis FROM {table_name} WHERE `内容hash`='{safe_hash}'"
            with engine.connect() as conn:
                df = pd.read_sql(check_sql, conn)
                df = df.copy()  # 复制数据避免与连接关联

            if not df.empty and df.iloc[0]['analysis'] == '1':
                logger.info(f"[火山方舟-聚合] 单条重试成功: {content_hash}")
            else:
                _increment_fail_count(table_name, content_hash)
                logger.warning(f"[火山方舟-聚合] 逐条重试失败，停止: {content_hash}")
                break
        except Exception as e:
            _increment_fail_count(table_name, content_hash)
            logger.error(f"[火山方舟-聚合] 单条重试异常: {content_hash}, {e}")
            break

        time.sleep(random.randint(1, 3))


def get_news_combine_analysis(table_name: str, analysis_table_name: str, _headless: bool = True) -> None:
    """获取并分析综合财经新闻"""
    from gs2026.analysis.worker.message.huoshanfangzhou.trading_day_util import get_start_end
    start_date, end_date = get_start_end()

    sql = (f"select SQL_NO_CACHE `内容hash`,`内容` from {table_name} "
           f"where (analysis is null or analysis='' or analysis LIKE 'fail_%%') "
           f"AND `发布时间` >= '{start_date}' AND `发布时间` <= '{end_date}' "
           f"order by RAND() limit 60")
    bk_dic_sql = "select name from data_industry_code_ths"
    gn_dic_sql = "select name from ths_gn_names_rq where flag='1'"

    try:
        with engine.connect() as conn:
            lists_df = pd.read_sql(sql, con=conn)
            lists = lists_df.copy().values.tolist()
            
            bk_df = pd.read_sql(bk_dic_sql, conn)
            bk_dic_str = ','.join(bk_df.copy()['name'].astype(str))
            
            gn_df = pd.read_sql(gn_dic_sql, conn)
            gn_dic_str = ','.join(gn_df.copy()['name'].astype(str))
    except Exception as e:
        logger.error(f"[火山方舟-聚合] 数据库查询异常: {e}")
        return False

    if len(lists) < 20:
        logger.info("[火山方舟-聚合] 数据量小于30，暂不处理")
        return False
    if len(lists) >= 20:
        sample_list = random.sample(lists, 20)
        volcengine_ai(sample_list, bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
        return True
    return False


def time_task_do_combine(polling_time: int, year: str = '2026') -> None:
    """定时轮询：持续对综合财经新闻执行AI分析"""
    while True:
        get_news_combine_analysis("news_combine" + year, "analysis_news" + year, True)
        time.sleep(polling_time)


if __name__ == "__main__":
    import argparse
    import json as json_lib

    parser = argparse.ArgumentParser(description='综合数据分析-火山方舟版')
    parser.add_argument('--params', type=str, help='JSON格式的参数')
    args = parser.parse_args()

    year = "2026"
    if args.params:
        try:
            params = json_lib.loads(args.params)
            if 'year' in params:
                year = params['year']
                logger.info(f'从参数获取年份: {year}')
        except json_lib.JSONDecodeError as e:
            logger.error(f'参数解析失败: {e}')

    run_daemon_task(target=time_task_do_combine, args=(10, year))
