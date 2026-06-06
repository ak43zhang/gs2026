"""财联社新闻数据 AI 分析模块 —— 火山方舟版本。

完全对齐 DeepSeek 版逻辑，仅替换 AI 调用层：
  - 不调用浏览器，走火山方舟 HTTP API
  - 删除敏感词替换
  - 删除 JSON 清理（直接 json.loads）
  - 其余逻辑（拒绝检测、失败计数、逐条重试、入库）完全一致
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
from gs2026.utils import log_util, string_enum, string_util
from gs2026.utils.task_runner import run_daemon_task
from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_client import (
    volcengine_analysis,
)

# 忽略 SQLAlchemy 的弃用警告
warnings.filterwarnings("ignore", category=SAWarning)

# ── 模块级初始化 ──────────────────────────────────────────────────────────────
logger = log_util.setup_logger(str(Path(__file__).absolute()))
pandas_display_config.set_pandas_display_options()

url: str = config_util.get_config('common.url')
deepseek_corpus_version_cls: str = config_util.get_config('common.deepseek_corpus_version.cls')

engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
mysql_tool = mysql_util.get_mysql_tool(url)

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
    """火山方舟AI分析主函数（接口与 deepseek_ai 完全一致）

    Args:
        query_list: [[内容hash, 内容], ...]
        bk_dic_str: 板块字典
        gn_dic_str: 概念字典
        table_name: 源数据表名
        analysis_table_name: 分析结果表名
        _headless: 兼容参数，忽略
        _is_retry: 是否为重试调用
    """
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

    # ── 构造完整 Prompt（与DeepSeek版完全一致） ─────────────────────────────
    query = query + f"""
                    请以顶级短线游资的角度分析上述{count}条消息进行逐一分析，返回结果为json对象，json 结构为

			        {{"消息集合": [
					    "消息id": "",
                        "板块详情": [
                            {{
                                "板块名称": "",
                                "板块明细": [
                                    {{
                                        "a股代码": "",
                                        "a股名称": "",
                                        "关联原因": "",
                                        "利好利空": ""
                                    }}
                                ]
                            }}
                        ],
                        "重要程度评分":"",
                        "业务影响维度评分":"",
                        "综合评分":"",
                        "深度分析":[""],
                        "消息大小": "",
                        "消息类型": "",
                        "涉及板块": [""],
                        "涉及概念": [""],
                        "龙头个股": [""]
					]}}

                    其中，消息id字段只存一个id
                    重要程度评分：按照 权威性与级别 角度评估程度分为 国家级政策（5分）、部委/地方政策（4分）、行业会议（3分）、公司公告（2分）、市场传闻（1分）。按照 新颖性与想象力 角度评估程度分为 新技术/新政策（5分）、现有产业数据向好（3分）。按照 相关性与纯度 角度评估程度分为 直接受益（核心业务高度相关）（5分）、间接受益（产业链上下游）（3分）、情绪相关（概念沾边）（1分），最终由三者分数相加，总分范围0至15分。
                    业务影响维度评分：（每个维度-5至5分，总分范围-60至60）
                        从12个关键经营维度评估消息的实质性影响，正面影响为正分，负面影响为负分，无影响为0分。评分时需结合消息内容具体分析。
                        按照 成本控制 维度评估程度分为	显著降低成本（5）、一定程度降低成本（3）、略有影响（1）	显著提高成本（-5）、一定程度提高（-3）、略有提高（-1），
                        按照 运营效率 维度评估程度分为	大幅提升效率（5）、有所提升（3）、轻微提升（1）	大幅降低效率（-5）、有所降低（-3）、轻微降低（-1），
                        按照 资金与财务 维度评估程度分为	极大改善现金流/利润（5）、明显改善（3）、略有改善（1）	极大恶化（-5）、明显恶化（-3）、略有恶化（-1），
                        按照 技术或工艺突破 维度评估程度分为	重大突破（5）、明显进步（3）、小幅改进（1）	技术落后（-5）、竞争力下降（-3）、小幅退步（-1），
                        按照 产品定价权 维度评估程度分为	显著增强定价能力（5）、有所增强（3）、轻微增强（1）	显著削弱（-5）、有所削弱（-3）、轻微削弱（-1），
                        按照 市场份额扩张 维度评估程度分为	大幅提升市占率（5）、明显提升（3）、小幅提升（1）	大幅下降（-5）、明显下降（-3）、小幅下降（-1），
                        按照 产业链地位 维度评估程度分为	大幅提升话语权（5）、有所提升（3）、轻微提升（1）	大幅降低（-5）、有所降低（-3）、轻微降低（-1），
                        按照 产品结构升级 维度评估程度分为	推动高端化/高附加值（5）、明显优化（3）、小幅调整（1）	导致低端化（-5）、明显劣化（-3）、小幅劣化（-1），
                        按照 成功拓展新业务 维度评估程度分为	开辟全新业务领域（5）、进入新市场（3）、尝试新方向（1）	退出核心业务（-5）、收缩业务（-3）、暂停拓展（-1），
                        按照 政策支持 维度评估程度分为	获得强力政策扶持（5）、一般性支持（3）、间接利好（1）	遭遇政策打压（-5）、限制（-3）、间接利空（-1），
                        按照 行业趋势红利 维度评估程度分为	处于爆发风口（5）、明显受益（3）、略有受益（1）	逆势而行（-5）、明显受损（-3）、略有受损（-1），
                        按照 输入成本下降 维度评估程度分为	大幅降低原材料/能源成本（5）、明显降低（3）、小幅降低（1）	大幅上升（-5）、明显上升（-3）、小幅上升（-1），
                        最终综合分析算出。
                    综合评分：（通过重要程度评分×4+业务影响维度评分）。
                    消息大小（由综合评分计算得出，重大：90 ≤ 综合评分，大：60 ≤ 综合评分 < 90，中：30 ≤ 综合评分 < 60，小：综合评分 < 30,字典值有重大，大，中，小四个）。
                    消息类型（由业务影响维度评分和综合评分分析得出，业务影响维度评分为负则为利空，综合评分小于0则为利空，0-60则为中性，大于60则为利好，字典值有利好、利空、中性三个字典值）。
                    涉及板块（涉及板块字典：{bk_dic_str}）。
                    涉及概念（涉及概念字典：{gn_dic_str}）。
                    利好利空（由业务影响维度评分和综合评分分析得出，业务影响维度评分为负则为利空，综合评分小于0则为利空，0-60则为中性，大于60则为利好，字典值有利好、利空、中性三个字典值）。
                    龙头个股（请根据成本控制、运营效率、资金与财务、技术或工艺突破、产品定价权、市场份额扩张、产业链地位、产品结构升级、成功拓展新业务、政策支持、行业趋势红利、输入成本下降等多个维度分析该消息直接受益或者受损的a股沪深板块股票代码，多值按照英文逗号分隔，6位代码）。
                    深度分析：(是根据成本控制、运营效率、资金与财务、技术或工艺突破、产品定价权、市场份额扩张、产业链地位、产品结构升级、成功拓展新业务、政策支持、行业趋势红利、输入成本下降等多个维度分析该消息的实质性影响,深度分析结果按照前面的维度+详细分析原因+维度评估程度分组成)。
                    结果返回能直接复制的完整的json数据。
            """

    # 调用火山方舟API获取AI分析结果（无敏感词替换）
    logger.info(f"[火山方舟-新闻] 开始分析: {count}条消息, IDs: {deal_id_list}")
    try:
        analysis: str = volcengine_analysis(query)
    except Exception as e:
        logger.error(f"[火山方舟-新闻] API调用异常: {e}")
        for item in query_list:
            _increment_fail_count(table_name, item[0])
        return

    # ── 拒绝检测 ─────────────────────────────────────────────────────────────
    if _is_refusal_response(analysis):
        logger.warning(f"[火山方舟-新闻] 拒绝回答批次（{count}条），原文: {analysis[:100]}...")
        if not _is_retry:
            _retry_one_by_one(query_list, bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
        else:
            logger.warning(f"[火山方舟-新闻] 重试中仍被拒绝，标记失败: {deal_id_list}")
            for item in query_list:
                _increment_fail_count(table_name, item[0])
        return

    if not analysis or analysis.strip() in ('', '{}'):
        logger.error(f"[火山方舟-新闻] 返回空结果，启动逐条重试")
        if not _is_retry:
            _retry_one_by_one(query_list, bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
        else:
            for item in query_list:
                _increment_fail_count(table_name, item[0])
        return

    # ── 解析 JSON 并写入数据库 ────────────────────────────────────────────────
    try:
        json_data = analysis.strip()
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
                f"('{table_name}','{analysis.strip()}','{update_time}','{deepseek_corpus_version_cls}')"
            )
            mysql_tool.update_transactions_data(update_sql1, update_sql2)

            # ③ 拆分入库 + 写 Redis 缓存
            try:
                from gs2026.analysis.worker.message.deepseek.news_result_processor import process_batch
                batch_stats = process_batch(analysis.strip(), table_name, deepseek_corpus_version_cls)
                logger.info(f"[火山方舟-新闻] 拆分入库完成: {batch_stats}")
            except Exception as proc_err:
                logger.error(f"[火山方舟-新闻] 拆分入库异常: {proc_err}")

            # ④ 未被成功分析的消息，增加失败计数
            success_ids = set(ids)
            for item in query_list:
                if item[0] not in success_ids:
                    _increment_fail_count(table_name, item[0])
        else:
            logger.error(f"[火山方舟-新闻] 未解析到有效消息ID，启动逐条重试")
            if not _is_retry:
                _retry_one_by_one(query_list, bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
            else:
                for item in query_list:
                    _increment_fail_count(table_name, item[0])

        logger.info(f"[火山方舟-新闻] 更新{table_name}表{ids_count}条数据")
    except JSONDecodeError:
        logger.error(f"[火山方舟-新闻] JSON解析失败,JSONDecodeError，启动逐条重试")
        logger.error(deal_id_list)
        if not _is_retry:
            _retry_one_by_one(query_list, bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
        else:
            for item in query_list:
                _increment_fail_count(table_name, item[0])
    except KeyError:
        logger.error(f"[火山方舟-新闻] JSON解析失败,KeyError，启动逐条重试")
        logger.error(deal_id_list)
        if not _is_retry:
            _retry_one_by_one(query_list, bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
        else:
            for item in query_list:
                _increment_fail_count(table_name, item[0])

    elapsed = time.time() - start
    logger.info(f"[火山方舟-新闻] {table_name}分析完成，耗时: {elapsed:.2f}秒")


def _retry_one_by_one(
    query_list: List[List[Any]],
    bk_dic_str: str,
    gn_dic_str: str,
    table_name: str,
    analysis_table_name: str,
    _headless: bool,
) -> None:
    """逐条重试，遇到第一个失败立即停止"""
    logger.info(f"[火山方舟-新闻] 逐条重试开始，共 {len(query_list)} 条")

    for item in query_list:
        content_hash = item[0]
        try:
            volcengine_ai([item], bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless, _is_retry=True)

            safe_hash = content_hash.replace("'", "\\'")
            check_sql = f"SELECT analysis FROM {table_name} WHERE `内容hash`='{safe_hash}'"
            with engine.connect() as conn:
                df = pd.read_sql(check_sql, conn)

            if not df.empty and df.iloc[0]['analysis'] == '1':
                logger.info(f"[火山方舟-新闻] 单条重试成功: {content_hash}")
            else:
                _increment_fail_count(table_name, content_hash)
                logger.warning(f"[火山方舟-新闻] 逐条重试失败，停止: {content_hash}")
                break
        except Exception as e:
            _increment_fail_count(table_name, content_hash)
            logger.error(f"[火山方舟-新闻] 单条重试异常: {content_hash}, {e}")
            break

        time.sleep(random.randint(1, 3))


def get_news_cls_analysis(table_name: str, analysis_table_name: str, _headless: bool = True) -> None:
    """获取并分析财联社新闻"""
    sql = (f"select SQL_NO_CACHE `内容hash`,`内容` from {table_name} "
           f"where (analysis is null or analysis='' or analysis LIKE 'fail_%%') "
           f"order by SUBSTRINg(`发布时间`,1,7) desc,rand() limit 60")
    bk_dic_sql = "select name from data_industry_code_ths"
    gn_dic_sql = "select name from ths_gn_names_rq where flag='1'"

    with engine.connect() as conn:
        lists = pd.read_sql(sql, con=conn).values.tolist()
        bk_dic_str = ','.join(pd.read_sql(bk_dic_sql, conn)['name'].astype(str))
        gn_dic_str = ','.join(pd.read_sql(gn_dic_sql, conn)['name'].astype(str))

        if len(lists) < 20:
            logger.info("[火山方舟-新闻] 数据量小于20，暂不处理")
            time.sleep(600)
            return
        if len(lists) >= 20:
            sample_list = random.sample(lists, 20)
            volcengine_ai(sample_list, bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)


def time_task_do_cls(polling_time: int, year: str = "2026") -> None:
    """定时轮询：持续对财联社新闻执行AI分析"""
    while True:
        get_news_cls_analysis("news_cls" + year, "analysis_news" + year, True)
        time.sleep(polling_time)


if __name__ == "__main__":
    import argparse
    import json as json_lib

    parser = argparse.ArgumentParser(description='财联社数据分析-火山方舟版')
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

    run_daemon_task(target=time_task_do_cls, args=(10, year))
