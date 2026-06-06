"""事件驱动分析——火山方舟版本

完全对齐 DeepSeek 版逻辑，仅替换 AI 调用层：
  - 不调用浏览器，走火山方舟 HTTP API
  - 删除敏感词替换
  - 删除 JSON 清理（直接使用原始返回）
  - 其余逻辑（Prompt、入库、拆分、锁、轮询）完全一致
"""

import time
import random
import warnings
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Any

import pandas as pd
import redis
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning

from gs2026.utils import (
    mysql_util, config_util, email_util,
    pandas_display_config, log_util
)
from gs2026.utils.decorators_util import db_retry
from gs2026.utils.task_runner import run_daemon_task

# 火山方舟客户端
from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_client import (
    volcengine_analysis, VolcengineClient
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
    火山方舟AI分析主函数（接口与 deepseek_ai / stepfun_ai 完全一致）

    Args:
        query_list: [(日期, 主领域, 子领域), ...]
        bk_dic_str: 板块字典字符串
        gn_dic_str: 概念字典字符串
        table_name: 源数据表名
        analysis_table_name: 分析结果表名
        _headless: 兼容参数，忽略
    """
    start = time.time()

    for i in query_list:
        t_date: str = i[0]
        main_area: str = i[1]
        child_area: str = i[2]

        # 构造分析prompt（与DeepSeek版完全一致）
        query = f"{t_date}全球重要大事件集锦，按重要程度给出30条主领域为{main_area}，子领域为{child_area}的消息，" + """
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
                    利空利好（由业务影响维度评分和综合评分分析得出，业务影响维度评分为负则为利空，综合评分小于0则为利空，0-60则为中性，大于60则为利好，字典值有利好、利空、中性三个字典值）。
                    消息大小（由综合评分计算得出，重大：90 ≤ 综合评分，大：60 ≤ 综合评分 < 90，中：30 ≤ 综合评分 < 60，小：综合评分 < 30,字典值有重大，大，中，小四个）。
                    涉及板块（板块字典："""+bk_dic_str+"""，以英文逗号分隔）。
                    涉及概念（概念字典："""+gn_dic_str+"""，以英文逗号分隔）。
                    股票代码（请根据成本控制、运营效率、资金与财务、技术或工艺突破、产品定价权、市场份额扩张、产业链地位、产品结构升级、成功拓展新业务、政策支持、行业趋势红利、输入成本下降等多个维度分析该消息直接受益或者受损的a股沪深板块股票代码，多值按照英文逗号分隔，6位代码），
                    时间（事件发表最早的时间，时间格式为yyyy-MM-dd HH:mm:ss），
                    事件来源（事件最早时间的来源）
                    原因分析（该字段主要根据成本控制、运营效率、资金与财务、技术或工艺突破、产品定价权、市场份额扩张、产业链地位、产品结构升级、成功拓展新业务、政策支持、行业趋势红利、输入成本下降等多个维度分析该消息对a股具体股票代码直接受益或者受损的原因）,
                    深度分析：(是根据成本控制、运营效率、资金与财务、技术或工艺突破、产品定价权、市场份额扩张、产业链地位、产品结构升级、成功拓展新业务、政策支持、行业趋势红利、输入成本下降等多个维度分析该消息的实质性影响,深度分析结果按照前面的维度+详细分析原因+维度评估程度分组成)
                    返回结果为json对象，json 结构为
			        {"消息集合": [
						"主领域": "",
						"子领域": "",
						"时间":"",
						"事件来源":"",
                        "关键事件": "",
                        "简要描述": "",
						"利空利好":"",
						"消息大小":"",
						"涉及板块": "",
						"涉及概念": "",
                        "股票代码": "",
                        "原因分析":"",
                        "重要程度评分":"",
                        "业务影响维度评分":"",
                        "综合评分":"",
                        "深度分析":[""]
					]}
					请返回json结果。
        """

        # 调用火山方舟API获取AI分析结果（无敏感词替换）
        logger.info(f"[火山方舟] 开始分析: {t_date} {main_area}-{child_area}")
        try:
            analysis: str = volcengine_analysis(query)
        except Exception as e:
            logger.error(f"[火山方舟] API调用异常: {e}")
            continue

        if not analysis or analysis.strip() in ('', '{}'):
            logger.error(f"[火山方舟] 返回空结果: {t_date} {main_area}-{child_area}")
            continue

        # 直接使用原始返回，不做JSON清理
        json_data = analysis.strip()

        # 验证并入库
        if json_data and json_data != '{}':
            # 写入分析结果表（兼容旧表结构）
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
            logger.error(f"[火山方舟] JSON解析失败: {table_name} {t_date} {main_area}-{child_area}")

    elapsed = time.time() - start
    logger.info(f"[火山方舟] {table_name} 分析完成，耗时: {elapsed:.2f}秒")


def area_ai_analysis(
    table_name: str,
    analysis_table_name: str,
    start_date: str,
    _headless: bool = True
) -> bool:
    """
    领域AI分析调度（接口与DeepSeek版完全一致）

    查询候选记录 → 获取锁 → 调用AI分析
    """
    # 查询尚未分析的候选记录
    sql = f"""
        select SQL_NO_CACHE '{start_date}' as t_date,
               {table_name}.main_area,
               {table_name}.child_area
        from {table_name}
        left join (select * from {analysis_table_name} where news_date='{start_date}') as analysis_area2
            on {table_name}.child_area = analysis_area2.child_area
        where is_use='1' and analysis_area2.news_date is null
        order by rand()
        limit 10
    """
    # 板块字典查询
    bk_dic_sql: str = "select name from data_industry_code_ths"
    # 概念字典查询（仅启用的概念）
    gn_dic_sql: str = "select name from ths_gn_names_rq where flag='1'"

    with engine.connect() as conn:
        candidates: List[dict] = pd.read_sql(sql, con=conn).to_dict('records')
        if not candidates:
            return False  # 无待处理任务，彻底结束

        # 将板块和概念名称拼接为逗号分隔的字符串
        bk_dic_str: str = ','.join(pd.read_sql(bk_dic_sql, conn)['name'].astype(str))
        gn_dic_str: str = ','.join(pd.read_sql(gn_dic_sql, conn)['name'].astype(str))

    # 遍历候选记录，尝试获取Redis分布式锁
    for cand in candidates:
        t_date: str = cand['t_date']
        main_area: str = cand['main_area']
        child_area: str = cand['child_area']

        # 分布式锁key（火山方舟前缀，避免与DeepSeek/StepFun冲突）
        lock_key: str = f"area_ai_lock:volcengine:{table_name}:{t_date}:{main_area}:{child_area}"
        lock = redis_client.lock(lock_key, timeout=900, blocking_timeout=0)

        if lock.acquire(blocking=False):
            try:
                # 成功获取锁，执行AI分析
                volcengine_ai(
                    [(t_date, main_area, child_area)],
                    bk_dic_str, gn_dic_str,
                    table_name, analysis_table_name,
                    _headless
                )
                return True  # 成功处理一条，本次调用结束
            except Exception as e:
                logger.error(f"[火山方舟] 处理失败 {t_date} {main_area}-{child_area}: {e}")
            finally:
                # 安全释放锁
                try:
                    lock.release()
                except redis.exceptions.LockNotOwnedError:
                    pass
        # 获取锁失败则跳过

    # 所有候选均被锁定或处理失败
    return True


def area_ai(area_ai_date: str, polling_time: int) -> None:
    """对指定日期执行领域AI分析的轮询循环"""
    flag: bool = True
    year: str = area_ai_date[0:4]
    table: str = "news_area"
    analysis_table: str = "analysis_area" + year

    while flag:
        flag = area_ai_analysis(table, analysis_table, area_ai_date, False)
        wait = random.randint(10, 30)
        time.sleep(wait)


def check_time_and_execute(
        target_date: datetime,
        check_interval: int,
        execute_func: Any,
        *func_args: Any,
        **func_kwargs: Any
) -> Any:
    """定时检查并在目标时间到达后执行指定函数"""
    logger.info(f"目标时间: {target_date.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("开始循环检查...")

    while True:
        current_time: datetime = datetime.now()

        if current_time > target_date:
            logger.info(f"\n✅ 时间已到！当前时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"开始执行: {execute_func.__name__}...")
            result = execute_func(*func_args, **func_kwargs)
            logger.info("任务执行完成")
            return result
        else:
            remaining = target_date - current_time
            days: int = remaining.days
            seconds: int = remaining.seconds
            hours: int = seconds // 3600
            minutes: int = (seconds % 3600) // 60
            current_minute: int = current_time.minute
            if current_minute % 10 == 0 or remaining.total_seconds() < 3600:
                logger.info(f"当前: {current_time.strftime('%H:%M:%S')}, "
                            f"剩余: {days}天{hours}小时{minutes}分钟")

        time.sleep(check_interval)


def analysis_event_driven(date_list_: List[str]) -> None:
    """事件驱动分析主入口，按日期列表依次执行全领域AI分析"""
    for area_date in date_list_:
        logger.info('=' * 30 + area_date + '=' * 30)
        area_ai(area_date, 1)


if __name__ == "__main__":
    import argparse
    import json as json_lib

    parser = argparse.ArgumentParser(description='事件驱动分析-火山方舟版')
    parser.add_argument('--params', type=str, help='JSON格式的参数')
    args = parser.parse_args()

    date_list = ['2026-06-05']

    if args.params:
        try:
            params = json_lib.loads(args.params)
            if 'date_list' in params:
                date_list = params['date_list']
                logger.info(f'从参数获取日期列表: {date_list}')
        except json_lib.JSONDecodeError as e:
            logger.error(f'参数解析失败: {e}')

    run_daemon_task(target=analysis_event_driven, args=(date_list,))
