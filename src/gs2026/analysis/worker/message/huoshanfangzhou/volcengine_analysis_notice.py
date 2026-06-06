"""公告数据AI分析模块 —— 火山方舟版本。

完全对齐 DeepSeek 版逻辑，仅替换 AI 调用层：
  - 不调用浏览器，走火山方舟 HTTP API
  - 删除敏感词替换
  - 其余逻辑（拒绝检测、失败计数、逐条重试、入库）完全一致
"""

import json
import random
import time
import warnings
from datetime import datetime
from json.decoder import JSONDecodeError
from pathlib import Path
from typing import List, Tuple, Any

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning

from gs2026.utils import (mysql_util, config_util, email_util,
                          pandas_display_config, log_util, string_util)
from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_client import volcengine_analysis
from gs2026.analysis.worker.message.deepseek.result_processor import process_notice
from gs2026.utils.task_runner import run_daemon_task

warnings.filterwarnings("ignore", category=SAWarning)

# ── 模块级初始化 ──────────────────────────────────────────────────────────────
logger = log_util.setup_logger(str(Path(__file__).absolute()))
pandas_display_config.set_pandas_display_options()

url: str = config_util.get_config("common.url")
deepseek_corpus_version_notice: str = config_util.get_config('common.deepseek_corpus_version.notice')

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
        logger.warning(f"公告 {content_hash} 失败 {current + 1} 次，标记为 skip")
    else:
        sql = f"UPDATE {table_name} SET analysis='fail_{current + 1}' WHERE `内容hash`='{safe_hash}'"
        logger.info(f"公告 {content_hash} 失败计数: {current} -> {current + 1}")
    mysql_tool.update_data(sql)


def volcengine_ai(
    query_list: List[Tuple[str, str, Any, str]],
    notice_type_dic_str: str,
    table_name: str,
    analysis_table_name: str,
    _headless: bool = True,
    _is_retry: bool = False,
) -> None:
    """火山方舟AI公告分析（接口与 deepseek_ai 完全一致）"""
    update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    start = time.time()
    count = len(query_list)
    deal_id_list = [row[0] for row in query_list]

    # ── 拼装公告文本 ──────────────────────────────────────────────────────────
    query = ""
    for i in query_list:
        content_hash = i[0]
        title = i[1]
        notice_date = str(i[2])
        stock_code = i[3]
        child_query = f"公告id：{content_hash}，公告日期：{notice_date}，股票代码：{stock_code}，标题为：{title} "
        query = query + child_query + "\n"

    # ── 构造完整 Prompt（与DeepSeek版完全一致） ─────────────────────────────
    query = query + f"""
                    请以顶级短线游资的角度分析上述{count}条公告，逐一分析每条公告对次日股价的影响。返回结果为json结构并且能够直接复制，json 结构为

			        {{"公告集合": [
                        {{
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
                        }}
                    ]}}

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
                    公告类型:（公告类型字典：{notice_type_dic_str}）

                    结果返回能直接复制的完整的json数据。
            """

    # 调用火山方舟API（无敏感词替换）
    logger.info(f"[火山方舟-公告] 开始分析: {count}条公告, IDs: {deal_id_list}")
    try:
        analysis: str = volcengine_analysis(query)
    except Exception as e:
        logger.error(f"[火山方舟-公告] API调用异常: {e}")
        for item in query_list:
            _increment_fail_count(table_name, item[0])
        return

    # ── 拒绝检测 ─────────────────────────────────────────────────────────────
    if _is_refusal_response(analysis):
        logger.warning(f"[火山方舟-公告] 拒绝回答批次（{count}条），原文: {analysis[:100]}...")
        if not _is_retry:
            _retry_one_by_one(query_list, notice_type_dic_str, table_name, analysis_table_name, _headless)
        else:
            logger.warning(f"[火山方舟-公告] 重试中仍被拒绝，标记失败: {deal_id_list}")
            for item in query_list:
                _increment_fail_count(table_name, item[0])
        return

    # ── 解析 JSON 并写入数据库 ────────────────────────────────────────────────
    try:
        from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_client import repair_llm_json, save_json_error
        analysis = repair_llm_json(analysis.strip())
        analysis_json: dict = json.loads(analysis)
        ids: List[str] = string_util.extract_message_ids(analysis_json, "公告集合", "公告id")
        ids_count = len(ids)

        if ids_count > 0 and analysis.strip() != '{}' and analysis != '':
            ids_str = "(" + ",".join(f"'{item}'" for item in ids) + ")"
            # ① 标记原始表已分析
            update_sql1 = f"UPDATE {table_name} SET analysis='1' WHERE `内容hash` in {ids_str}"
            # ② 写入分析结果表
            update_sql2 = (
                f"INSERT INTO {analysis_table_name} "
                f"(table_name,json_value,update_time,version) VALUES "
                f"('{table_name}','{analysis}','{update_time}','{deepseek_corpus_version_notice}')"
            )
            mysql_tool.update_transactions_data(update_sql1, update_sql2)

            # ③ 拆分入库
            try:
                stats = process_notice(analysis, version=deepseek_corpus_version_notice)
                logger.info(f"[火山方舟-公告] 拆分入库完成: {stats}")
            except Exception as e:
                logger.error(f"[火山方舟-公告] 拆分入库失败: {e}")

            # ④ 未被成功分析的公告，增加失败计数
            success_ids = set(ids)
            for item in query_list:
                if item[0] not in success_ids:
                    _increment_fail_count(table_name, item[0])
        else:
            logger.error(f"[火山方舟-公告] 未解析到有效公告ID，启动逐条重试")
            if not _is_retry:
                _retry_one_by_one(query_list, notice_type_dic_str, table_name, analysis_table_name, _headless)
            else:
                for item in query_list:
                    _increment_fail_count(table_name, item[0])

        logger.info(f"[火山方舟-公告] 更新{table_name}表{ids_count}条数据")
    except JSONDecodeError as e:
        save_json_error('volcengine_notice', analysis.strip() if analysis else '', str(e))
        logger.error(f"[火山方舟-公告] JSON解析失败,JSONDecodeError（已保存），启动逐条重试")
        logger.error(deal_id_list)
        if not _is_retry:
            _retry_one_by_one(query_list, notice_type_dic_str, table_name, analysis_table_name, _headless)
        else:
            for item in query_list:
                _increment_fail_count(table_name, item[0])
    except KeyError:
        logger.error(f"[火山方舟-公告] JSON解析失败,KeyError，启动逐条重试")
        logger.error(deal_id_list)
        if not _is_retry:
            _retry_one_by_one(query_list, notice_type_dic_str, table_name, analysis_table_name, _headless)
        else:
            for item in query_list:
                _increment_fail_count(table_name, item[0])

    elapsed = time.time() - start
    logger.info(f"[火山方舟-公告] {table_name}分析完成，耗时: {elapsed:.2f}秒")


def _retry_one_by_one(
    query_list: List[Tuple[str, str, Any, str]],
    notice_type_dic_str: str,
    table_name: str,
    analysis_table_name: str,
    _headless: bool,
) -> None:
    """逐条重试，遇到第一个失败立即停止"""
    logger.info(f"[火山方舟-公告] 逐条重试开始，共 {len(query_list)} 条")

    for item in query_list:
        content_hash = item[0]
        try:
            volcengine_ai([item], notice_type_dic_str, table_name, analysis_table_name, _headless, _is_retry=True)

            safe_hash = content_hash.replace("'", "\\'")
            check_sql = f"SELECT analysis FROM {table_name} WHERE `内容hash`='{safe_hash}'"
            with engine.connect() as conn:
                df = pd.read_sql(check_sql, conn)

            if not df.empty and df.iloc[0]['analysis'] == '1':
                logger.info(f"[火山方舟-公告] 单条重试成功: {content_hash}")
            else:
                _increment_fail_count(table_name, content_hash)
                logger.warning(f"[火山方舟-公告] 逐条重试失败，停止: {content_hash}")
                break
        except Exception as e:
            _increment_fail_count(table_name, content_hash)
            logger.error(f"[火山方舟-公告] 单条重试异常: {content_hash}, {e}")
            break

        time.sleep(random.randint(2, 5))


def get_notice_analysis(table_name: str, analysis_table_name: str, _headless: bool = True) -> bool:
    """查询未分析的公告数据并触发AI分析"""
    from gs2026.analysis.worker.message.huoshanfangzhou.trading_day_util import get_start_end
    start_date, end_date = get_start_end()

    sql = (f"select SQL_NO_CACHE `内容hash`,`公告标题`,`公告日期`,`代码` from {table_name} "
           f"where (analysis is null or analysis='' or analysis LIKE 'fail_%%') "
           f"AND `公告日期` >= '{start_date}' AND `公告日期` <= '{end_date}' "
           f"order by rand() desc limit 40")
    notice_type_dic_sql = "select type from notice_type where flag='1'"
    print(sql)

    with engine.connect() as conn:
        lists = pd.read_sql(sql, con=conn).values.tolist()
        notice_type_dic_str = ','.join(pd.read_sql(notice_type_dic_sql, conn)['type'].astype(str))

        if 0 < len(lists) < 20:
            volcengine_ai(lists, notice_type_dic_str, table_name, analysis_table_name, _headless)
        elif len(lists) >= 20:
            sample_list = random.sample(lists, random.randint(15, 18))
            volcengine_ai(sample_list, notice_type_dic_str, table_name, analysis_table_name, _headless)
        else:
            return False
    return True


def timer_task_do_notice(polling_time: int, year: str = "2026") -> None:
    """持续轮询执行公告AI分析"""
    while True:
        flag = get_notice_analysis(f"jhsaggg{year}", f"analysis_notices{year}", True)
        if not flag:
            logger.info(f"[火山方舟-公告] 公告分析完成，年份: {year}")
            break
        wait = random.randint(10, 30)
        time.sleep(wait)


if __name__ == "__main__":
    import argparse
    import json as json_lib

    parser = argparse.ArgumentParser(description='公告分析-火山方舟版')
    parser.add_argument('--params', type=str, help='JSON格式的参数')
    args = parser.parse_args()

    year = "2026"
    polling_time = 1
    if args.params:
        try:
            params = json_lib.loads(args.params)
            if 'year' in params:
                year = params['year']
            if 'polling_time' in params:
                polling_time = int(params['polling_time'])
        except json_lib.JSONDecodeError as e:
            logger.error(f'参数解析失败: {e}')

    run_daemon_task(target=timer_task_do_notice, args=(polling_time, year), daemon=False)
