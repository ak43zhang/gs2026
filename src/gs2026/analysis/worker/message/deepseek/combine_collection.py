"""调度采集总线模块——每日数据采集的统一入口。

本模块负责协调和调度所有每日数据采集任务，包括涨停板数据、基础行情数据、
问财数据、债券数据、风险数据和板块概念数据的采集。采集流程按固定顺序依次执行，
部分任务通过事件驱动机制在指定时间点触发。

核心功能:
    - 统一调度六大类数据采集任务（涨停、基础、问财、债券、风险、板块概念）
    - 基于事件驱动的定时采集（等待指定时间后自动执行）
    - 采集异常时通过邮件告警通知相关人员
    - 完整的日志记录和耗时统计

依赖关系:
    - gs2026.collection: 各类数据采集器（涨停、基础行情、问财、债券、风险等）
    - gs2026.analysis.worker.message.deepseek: 事件驱动调度器
    - gs2026.utils: 数据库工具、配置工具、邮件工具等基础设施
    - SQLAlchemy: 数据库连接管理
    - pandas: 数据查询与处理
"""

import warnings
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning
from loguru import logger

from gs2026.utils import mysql_util, config_util, email_util, pandas_display_config
from gs2026.utils.decorators_util import log_decorator, timing

from gs2026.analysis.worker.message.deepseek import deepseek_analysis_event_driven
from gs2026.collection.base import (
    zt_collection,
    base_collection,
    baostock_collection,
    bk_gn_collection,
    wencai_collection,
)
from gs2026.collection.other import bond_zh_cov
from gs2026.collection.risk import (
    akshare_risk_history,
    notice_risk_history,
    wencai_risk_history,
    wencai_risk_year_history,
)


# 忽略 SQLAlchemy 的反射警告，避免日志噪音
warnings.filterwarnings("ignore", category=SAWarning)
# 设置 pandas 全局显示配置（列宽、行数等）
pandas_display_config.set_pandas_display_options()

# 从配置文件读取数据库连接 URL
url: str = config_util.get_config('common.url')

# 初始化数据库连接引擎，启用连接池回收和预检机制
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()
# 初始化 MySQL 工具和邮件工具实例
mysql_tool = mysql_util.get_mysql_tool(url)
email_tool = email_util.EmailUtil()


@log_decorator(log_level="INFO", log_args=True, log_result=True)
@timing
def run_ztb_collection(start_time: str, end_time: str, base_date: datetime) -> None:
    """采集涨停板相关数据。

    等待至基准日期的 17:30 后开始采集涨停板查询数据，
    随后采集涨停占比统计数据。

    Args:
        start_time: 采集起始日期，格式为 'YYYY-MM-DD'。
        end_time: 采集结束日期，格式为 'YYYY-MM-DD'。
        base_date: 基准日期，用于计算目标触发时间（17:30）。

    Returns:
        None

    """

    # 设定涨停数据采集的目标触发时间为当日 17:30
    target_time: datetime = base_date.replace(hour=17, minute=30, second=0)
    # 通过事件驱动机制等待目标时间后执行涨停板查询采集
    deepseek_analysis_event_driven.check_time_and_execute(
        target_date=target_time,
        check_interval=60,
        execute_func=zt_collection.collect_ztb_query,
        start_date=start_time,
        end_date=end_time
    )
    # 采集涨停占比统计数据
    zt_collection.collect_zt_zb_collection(start_time, end_time)
    logger.info(f"涨停数据采集完成: {start_time} ~ {end_time}")


@log_decorator(log_level="INFO", log_args=True)
@timing
def run_base_collection(start_time: str, end_time: str, base_date: datetime) -> None:
    """采集基础行情数据。

    等待至基准日期的 22:00 后开始采集基础行情数据，
    随后采集 BaoStock 数据源的行情数据。

    Args:
        start_time: 采集起始日期，格式为 'YYYY-MM-DD'。
        end_time: 采集结束日期，格式为 'YYYY-MM-DD'。
        base_date: 基准日期，用于计算目标触发时间（22:00）。

    Returns:
        None
    """
    # 设定基础数据采集的目标触发时间为当日 22:00
    target_time: datetime = base_date.replace(hour=22, minute=0, second=0)
    # 等待目标时间后执行基础行情采集
    deepseek_analysis_event_driven.check_time_and_execute(
        target_date=target_time,
        check_interval=60,
        execute_func=base_collection.get_base_collect,
        start_date=start_time,
        end_date=end_time
    )
    # 采集 BaoStock 数据源的补充行情数据
    baostock_collection.get_baostock_collection(start_time, end_time)
    logger.info(f"基础数据采集完成: {start_time} ~ {end_time}")


@log_decorator(log_level="INFO", log_args=True)
@timing
def run_wencai_collection(start_time: str, end_time: str, next_jy_time: str) -> None:
    """采集问财（iFind）数据。

    包括基础查询数据和人气排名数据的采集。

    Args:
        start_time: 采集起始日期，格式为 'YYYY-MM-DD'。
        end_time: 采集结束日期，格式为 'YYYY-MM-DD'。
        next_jy_time: 下一个交易日日期，格式为 'YYYY-MM-DD'。

    Returns:
        None
    """
    # 采集问财基础查询数据（使用下一个交易日作为查询范围）
    wencai_collection.collect_base_query(next_jy_time, next_jy_time,True)
    # 采集问财人气排名数据
    wencai_collection.collect_popularity_query(start_time, end_time,True)
    logger.info(f"问财数据采集完成")


@log_decorator(log_level="INFO", log_args=True)
@timing
def run_bond_collection() -> None:
    """采集可转债相关数据。

    包括可转债基础信息和日线行情数据的采集。

    Returns:
        None
    """
    # 采集可转债基础信息
    bond_zh_cov.get_bond()
    # 采集可转债日线行情数据
    bond_zh_cov.get_bond_daily()
    logger.info("债券数据采集完成")


@log_decorator(log_level="INFO", log_args=True)
@timing
def run_risk_collection(
    day_ago_10_time: str,
    day_ago_5_time: str,
    start_time: str,
    end_time: str,
    next_jy_time: str
) -> None:
    """采集多维度风险数据。

    从 AKShare、公告、问财等多个数据源采集风险相关数据，
    用于后续的风险评估和预警分析。

    Args:
        day_ago_10_time: 10天前的日期，格式为 'YYYY-MM-DD'。
        day_ago_5_time: 5天前的日期，格式为 'YYYY-MM-DD'。
        start_time: 采集起始日期，格式为 'YYYY-MM-DD'。
        end_time: 采集结束日期，格式为 'YYYY-MM-DD'。
        next_jy_time: 下一个交易日日期，格式为 'YYYY-MM-DD'。

    Returns:
        None
    """
    # 采集 AKShare 风险历史数据（近10天范围）
    akshare_risk_history.akshare_risk_collect(day_ago_10_time, next_jy_time)
    # 采集公告原始数据
    notice_risk_history.notice_collect(day_ago_10_time, next_jy_time)
    # 采集公告风险评估数据
    notice_risk_history.notice_risk_collect(day_ago_10_time, next_jy_time)
    # 采集问财风险数据（近5天范围）
    wencai_risk_history.wencai_risk_collect(day_ago_5_time, next_jy_time)
    # 采集问财年度风险数据
    wencai_risk_year_history.wencai_risk_year_collect(start_time, end_time)
    logger.info(f"风险数据采集完成")


@log_decorator(log_level="INFO", log_args=True, log_result=True)
@timing
def run_bk_gn_collection(start_time: str, end_time: str) -> None:
    """采集板块概念数据。

    采集东方财富板块概念分类及相关行情数据。

    Args:
        start_time: 采集起始日期，格式为 'YYYY-MM-DD'。
        end_time: 采集结束日期，格式为 'YYYY-MM-DD'。

    Returns:
        None
    """
    bk_gn_collection.bk_gn_collect(start_time, end_time)
    logger.info(f"板块概念数据采集完成: {start_time} ~ {end_time}")


@log_decorator(log_level="INFO", log_args=True, log_exception=True)
@timing
def main_collection_pipeline(base_date: datetime) -> bool:
    """主采集流水线——按顺序执行全部六大采集任务。

    依次执行涨停、基础行情、问财、债券、风险、板块概念六大类数据采集，
    并在每个阶段记录详细日志。任一阶段异常将中断后续流程并向上抛出异常。

    Args:
        base_date: 基准日期，所有采集任务的日期参数均基于此日期计算。

    Returns:
        bool: 采集流程全部成功返回 True。

    Raises:
        Exception: 任一采集任务失败时向上传播异常。

    """

    logger.info(f"{'=' * 60}")
    logger.info(f"开始采集流程 - 基准日期: {base_date.strftime('%Y-%m-%d')}")
    logger.info(f"{'=' * 60}")

    try:
        # ---- 日期参数计算 ----
        next_date: datetime = base_date + timedelta(days=1)
        day_ago_5: datetime = base_date + timedelta(days=-5)
        day_ago_10: datetime = base_date + timedelta(days=-10)

        start_time: str = base_date.strftime('%Y-%m-%d')
        end_time: str = base_date.strftime('%Y-%m-%d')
        next_time: str = next_date.strftime('%Y-%m-%d')
        day_ago_5_time: str = day_ago_5.strftime('%Y-%m-%d')
        day_ago_10_time: str = day_ago_10.strftime('%Y-%m-%d')

        # 查询交易日历表获取下一个有效交易日
        next_time_sql: str = (
            f"SELECT trade_date FROM data_jyrl "
            f"WHERE trade_date>'{start_time}' "
            f"AND trade_status='1' LIMIT 1"
        )
        next_jy_time: str = pd.read_sql(next_time_sql, con=con).values.tolist()[0][0]
        logger.info(f"下一个交易日: {next_jy_time}")

        # 1. 涨停数据采集
        logger.info("[1/6] 开始采集涨停数据...")
        run_ztb_collection(start_time, end_time, base_date)

        # 2. 基础数据采集
        logger.info("[2/6] 开始采集基础数据...")
        run_base_collection(start_time, end_time, base_date)

        # 3. 问财数据采集
        logger.info("[3/6] 开始采集问财数据...")
        run_wencai_collection(start_time, end_time, next_jy_time)

        # 4. 债券数据采集
        logger.info("[4/6] 开始采集债券数据...")
        run_bond_collection()

        # 5. 风险数据采集
        logger.info("[5/6] 开始采集风险数据...")
        run_risk_collection(day_ago_10_time, day_ago_5_time, start_time, end_time, next_jy_time)

        # 6. 板块概念数据采集
        logger.info("[6/6] 开始采集板块概念数据...")
        run_bk_gn_collection(start_time, end_time)

        logger.info(f"{'=' * 60}")
        logger.info("所有数据采集完成！")
        logger.info(f"{'=' * 60}")

        return True

    except Exception as e:
        logger.exception(f"采集流程异常: {e}")
        raise


if __name__ == "__main__":
    base_date = datetime(2026, 4, 21)
    main_collection_pipeline(base_date)
