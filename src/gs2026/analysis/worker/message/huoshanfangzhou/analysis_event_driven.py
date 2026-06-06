"""事件驱动分析——火山方舟版本

完全兼容原DeepSeek/StepFun版本接口，仅替换AI调用层：
  - 使用火山方舟HTTP API（OpenAI兼容格式）
  - 复用prompts和result_processor
  - 保持所有输入输出不变
"""

import time
import warnings
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import pandas as pd
import redis
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning

from gs2026.utils import (
    mysql_util, config_util, email_util,
    pandas_display_config, log_util, string_util
)
from gs2026.utils.decorators_util import db_retry
from gs2026.utils.task_runner import run_daemon_task

# 导入火山方舟组件
from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_client import (
    volcengine_analysis, VolcengineClient
)

# 复用Prompt（模型无关）
from gs2026.analysis.worker.message.stepfun.prompts import (
    SYSTEM_PROMPT_EVENT_DRIVEN,
    EVENT_DRIVEN_PROMPT_TEMPLATE
)

# 复用结果处理器（保持表结构兼容）
from gs2026.analysis.worker.message.deepseek.result_processor import process_domain

warnings.filterwarnings("ignore", category=SAWarning)

# ===== 模块初始化 =====
logger = log_util.setup_logger(str(Path(__file__).absolute()))
pandas_display_config.set_pandas_display_options()

url: str = config_util.get_config("common.url")
redis_host: str = config_util.get_config('common.redis.host')
redis_port: int = config_util.get_int('common.redis.port')

engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
mysql_tool = mysql_util.get_mysql_tool(url)
email_util_inst = email_util.EmailUtil()

redis_client: redis.Redis = redis.Redis(
    host=redis_host, port=redis_port, decode_responses=True
)


def volcengine_ai(
    query_list: List[Tuple[str, str, str]],
    bk_dic_str: str,
    gn_dic_str: str,
    table_name: str,
    analysis_table_name: str,
    _headless: bool = True
) -> None:
    """
    火山方舟AI分析主函数（完全兼容 deepseek_ai / stepfun_ai 接口）

    Args:
        query_list: [(日期, 主领域, 子领域), ...]
        bk_dic_str: 板块字典字符串
        gn_dic_str: 概念字典字符串
        table_name: 源数据表名
        analysis_table_name: 分析结果表名
        _headless: 兼容参数，忽略
    """
    start = time.time()
    update_time: str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for item in query_list:
        t_date: str = item[0]
        main_area: str = item[1]
        child_area: str = item[2]

        # 构造Prompt（使用字符串替换避免format冲突）
        query = EVENT_DRIVEN_PROMPT_TEMPLATE
        query = query.replace('__MAIN_AREA__', main_area)
        query = query.replace('__CHILD_AREA__', child_area)
        query = query.replace('__BK_DIC_STR__', bk_dic_str)
        query = query.replace('__GN_DIC_STR__', gn_dic_str)
        query = query.replace('__QUERY__', f"{t_date}全球重要事件")

        # 敏感词替换
        query = string_util.sensitive_word_replacement(query)

        # 调用火山方舟API
        logger.info(f"[火山方舟] 开始分析: {t_date} {main_area}-{child_area}")
        try:
            analysis: str = volcengine_analysis(query, _headless)
        except Exception as e:
            logger.error(f"[火山方舟] API调用异常: {e}")
            continue

        if not analysis or analysis.strip() in ('', '{}'):
            logger.error(f"[火山方舟] 返回空结果: {t_date} {main_area}-{child_area}")
            continue

        # 清理JSON（复用原有逻辑）
        analysis = string_util.remove_json_prefix(analysis, 'json')
        analysis = string_util.remove_json_prefix(analysis, 'Copy')
        analysis = string_util.remove_json_comments(analysis)
        analysis = analysis.lstrip()

        json_data, _ = string_util.extract_json_from_string(analysis)

        if string_util.is_valid_json(json_data) and json_data != '{}':
            # 写入分析结果表
            update_sql = (
                f"INSERT INTO {analysis_table_name} "
                f"(news_date, main_area, child_area, json_data) VALUES "
                f"('{t_date}', '{main_area}', '{child_area}', "
                f"'{json_data.replace(chr(39), chr(39)+chr(39))}')"
            )
            mysql_tool.update_data(update_sql)

            # 拆分入库新表
            try:
                stats = process_domain(
                    json_data, main_area, child_area, t_date, version='volcengine-1.0.0'
                )
                logger.info(f"[火山方舟] 拆分入库完成: {stats}")
            except Exception as e:
                logger.error(f"[火山方舟] 拆分入库失败: {e}")
        else:
            logger.error(f"[火山方舟] JSON解析失败: {table_name}")

    elapsed = time.time() - start
    logger.info(f"[火山方舟] {table_name} 分析完成，耗时: {elapsed:.2f}秒")


def area_ai_analysis(
    table_name: str,
    analysis_table_name: str,
    start_date: str,
    _headless: bool = True
) -> bool:
    """
    领域AI分析调度（完全兼容原接口）
    """
    # 查询候选记录
    sql = f"""
        SELECT '{start_date}' as t_date,
               {table_name}.main_area,
               {table_name}.child_area
        FROM {table_name}
        LEFT JOIN (
            SELECT * FROM {analysis_table_name}
            WHERE news_date = '{start_date}'
        ) AS analyzed ON {table_name}.child_area = analyzed.child_area
        WHERE is_use = '1' AND analyzed.news_date IS NULL
        ORDER BY RAND()
        LIMIT 10
    """

    bk_sql = "SELECT name FROM data_industry_code_ths"
    gn_sql = "SELECT name FROM ths_gn_names_rq WHERE flag = '1'"

    with engine.connect() as conn:
        candidates = pd.read_sql(sql, conn).to_dict('records')
        if not candidates:
            return False

        bk_dic_str = ','.join(pd.read_sql(bk_sql, conn)['name'].astype(str))
        gn_dic_str = ','.join(pd.read_sql(gn_sql, conn)['name'].astype(str))

    # 尝试获取锁并处理
    for cand in candidates:
        t_date = cand['t_date']
        main_area = cand['main_area']
        child_area = cand['child_area']

        lock_key = f"area_ai_lock:volcengine:{table_name}:{t_date}:{main_area}:{child_area}"
        lock = redis_client.lock(lock_key, timeout=900, blocking_timeout=0)

        if lock.acquire(blocking=False):
            try:
                volcengine_ai(
                    [(t_date, main_area, child_area)],
                    bk_dic_str, gn_dic_str,
                    table_name, analysis_table_name,
                    _headless
                )
                return True
            except Exception as e:
                logger.error(f"[火山方舟] 处理失败: {e}")
            finally:
                try:
                    lock.release()
                except redis.exceptions.LockNotOwnedError:
                    pass

    return True


def area_ai(area_ai_date: str, polling_time: int) -> None:
    """轮询循环"""
    flag = True
    year = area_ai_date[:4]
    table = "news_area"
    analysis_table = f"analysis_area{year}"

    while flag:
        flag = area_ai_analysis(table, analysis_table, area_ai_date, True)
        time.sleep(polling_time)


def analysis_event_driven(date_list_: List[str]) -> None:
    """主入口"""
    for area_date in date_list_:
        logger.info(f"[火山方舟] {'='*30}{area_date}{'='*30}")
        area_ai(area_date, 1)


if __name__ == "__main__":
    import argparse
    import json as json_lib

    parser = argparse.ArgumentParser(description='事件驱动分析-火山方舟版')
    parser.add_argument('--params', type=str, help='JSON参数')
    args = parser.parse_args()

    date_list = ['2026-06-05', '2026-06-06']

    if args.params:
        try:
            params = json_lib.loads(args.params)
            date_list = params.get('date_list', date_list)
        except json_lib.JSONDecodeError as e:
            logger.error(f"参数解析失败: {e}")

    run_daemon_task(target=analysis_event_driven, args=(date_list,))
