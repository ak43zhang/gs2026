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
from gs2026.utils import log_util, string_enum, string_util
from gs2026.utils.task_runner import run_daemon_task
from gs2026.analysis.worker.message.deepseek import deepseek_analysis_event_driven

# 忽略 SQLAlchemy 的弃用警告，避免日志噪音
warnings.filterwarnings("ignore", category=SAWarning)

# ── 模块级初始化 ──────────────────────────────────────────────────────────────
logger = log_util.setup_logger(str(Path(__file__).absolute()))
pandas_display_config.set_pandas_display_options()

# 数据库连接配置
url: str = config_util.get_config('common.url')
deepseek_corpus_version_cls: str = config_util.get_config('common.deepseek_corpus_version.cls')

engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
browser_path: str = string_enum.FIREFOX_PATH_1509
mysql_tool = mysql_util.get_mysql_tool(url)

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

    # ── 构造完整 Prompt（包含评分体系与字典约束） ─────────────────────────────
    query = query + f"""
                    请以顶级短线游资的角度分析上述""" + str(count) + """条消息进行逐一分析，返回结果为json对象，json 结构为
                
			        {"消息集合": [
					    "消息id": "",
                        "板块详情": [
                            {
                                "板块名称": "",
                                "板块明细": [
                                    {
                                        "a股代码": "",
                                        "a股名称": "",
                                        "关联原因": "",
                                        "利好利空": ""
                                    }
                                    ]
                                }
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
					]}
                
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
                    涉及板块（涉及板块字典：""" + bk_dic_str + """）。
                    涉及概念（涉及概念字典：""" + gn_dic_str + """）。
                    利好利空（由业务影响维度评分和综合评分分析得出，业务影响维度评分为负则为利空，综合评分小于0则为利空，0-60则为中性，大于60则为利好，字典值有利好、利空、中性三个字典值）。
                    龙头个股（请根据成本控制、运营效率、资金与财务、技术或工艺突破、产品定价权、市场份额扩张、产业链地位、产品结构升级、成功拓展新业务、政策支持、行业趋势红利、输入成本下降等多个维度分析该消息直接受益或者受损的a股沪深板块股票代码，多值按照英文逗号分隔，6位代码）。
                    深度分析：(是根据成本控制、运营效率、资金与财务、技术或工艺突破、产品定价权、市场份额扩张、产业链地位、产品结构升级、成功拓展新业务、政策支持、行业趋势红利、输入成本下降等多个维度分析该消息的实质性影响,深度分析结果按照前面的维度+详细分析原因+维度评估程度分组成)。
                    结果返回能直接复制的完整的json数据。
            """
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
                from gs2026.analysis.worker.message.deepseek.news_result_processor import process_batch
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
    """从数据库拉取待分析的财联社新闻并交由 AI 分析。

    根据数据量大小进行随机采样，控制单次分析批量：
    - 数据量 < 5：暂不处理，休眠 10 分钟后返回
    - 5 ≤ 数据量 < 20：随机采样 0~全部
    - 数据量 ≥ 20：随机采样 15~18 条

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

        if len(lists) < 5:
            # 数据量过少，暂不处理，等待更多数据积累
            logger.info("当前数据量小于5。暂不处理")
            time.sleep(600)
        if 5 <= len(lists) < 20:
            # 中等数据量，随机采样部分消息
            sample_list: List[List[Any]] = random.sample(lists, random.randint(0, len(lists)))
            deepseek_ai(sample_list, bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
        if len(lists) >= 20:
            # 大数据量，采样 15~18 条保证分析效率
            sample_list = random.sample(lists, random.randint(15, 18))
            deepseek_ai(sample_list, bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)


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
