"""火山方舟单账号串行调度器

确保同一时刻只有一个模块在调用API，轮询执行所有分析任务。
当所有模块无数据时等待30s，永不退出。
"""
import time
from datetime import datetime
from typing import List

from loguru import logger

from gs2026.analysis.worker.message.huoshanfangzhou.trading_day_util import (
    get_date_list_until_yesterday,
)


# ============ 配置 ============
IDLE_WAIT = 30   # 全部无数据时等待秒数
TASK_GAP = 2     # 任务间间隔秒数
YEAR = "2026"


# ============ 各模块包装函数 ============

def _run_event_driven() -> bool:
    """事件驱动分析：检查是否有未分析数据，有则执行一轮"""
    from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_analysis_event_driven import area_ai_analysis
    from gs2026.utils import config_util
    from sqlalchemy import create_engine
    import pandas as pd

    date_list = get_date_list_until_yesterday()
    if not date_list:
        return False

    url = config_util.get_config("common.url")
    _engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)

    table_name = "news_area"
    analysis_table_name = f"analysis_area{YEAR}"

    has_data = False
    for area_date in date_list:
        # 检查是否有未分析的领域（左连接查已分析，筛未分析的）
        sql = (f"SELECT COUNT(1) as cnt FROM {table_name} t "
               f"LEFT JOIN (SELECT * FROM {analysis_table_name} WHERE news_date='{area_date}') a "
               f"ON t.child_area = a.child_area "
               f"WHERE t.is_use='1' AND a.news_date IS NULL")
        try:
            with _engine.connect() as conn:
                df = pd.read_sql(sql, conn)
                cnt = df.copy().iloc[0]['cnt']
            if cnt > 0:
                has_data = True
                logger.info(f"[调度器-事件驱动] {area_date} 有 {cnt} 条待分析")
                area_ai_analysis(table_name, analysis_table_name, area_date, False)
        except Exception as e:
            logger.error(f"[调度器-事件驱动] 查询异常: {e}")

    return has_data


def _run_cls() -> bool:
    """财联社新闻分析：执行一批"""
    from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_analysis_news_cls import get_news_cls_analysis
    try:
        return get_news_cls_analysis(f"news_cls{YEAR}", f"analysis_news{YEAR}", True)
    except Exception as e:
        logger.error(f"[调度器-CLS] 执行异常: {e}")
        return False


def _run_combine() -> bool:
    """综合新闻分析：执行一批"""
    from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_analysis_news_combine import get_news_combine_analysis
    try:
        return get_news_combine_analysis(f"news_combine{YEAR}", f"analysis_news{YEAR}", True)
    except Exception as e:
        logger.error(f"[调度器-聚合] 执行异常: {e}")
        return False


def _run_ztb() -> bool:
    """涨停板分析：检查是否有未分析数据"""
    from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_analysis_news_ztb import time_task_do_ztb

    date_list = get_date_list_until_yesterday()
    if not date_list:
        return False

    has_data = False
    for area_date in date_list:
        try:
            # time_task_do_ztb 内部会查询并处理
            time_task_do_ztb(area_date, area_date, area_date, 10)
            has_data = True  # 只要执行了就算有数据
        except Exception as e:
            logger.error(f"[调度器-涨停] {area_date} 异常: {e}")

    return has_data


def _run_notice() -> bool:
    """公告分析：执行一批"""
    from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_analysis_notice import get_notice_analysis
    try:
        return get_notice_analysis(f"jhsaggg{YEAR}", f"analysis_notices{YEAR}", True)
    except Exception as e:
        logger.error(f"[调度器-公告] 执行异常: {e}")
        return False


# ============ 调度器主循环 ============

TASKS: List[tuple] = [
    # ("event_driven", _run_event_driven),
    ("news_cls", _run_cls),
    # ("news_ztb", _run_ztb),
    ("news_combine", _run_combine),
    ("notice", _run_notice),
]


def run_scheduler():
    """主循环：永久轮询，永不退出"""
    logger.info("=" * 50)
    logger.info("[调度器] 火山方舟串行调度器启动")
    logger.info(f"[调度器] 任务列表: {[t[0] for t in TASKS]}")
    logger.info(f"[调度器] 空闲等待: {IDLE_WAIT}s | 任务间隔: {TASK_GAP}s")
    logger.info("=" * 50)

    round_num = 0
    while True:
        round_num += 1
        round_has_data = False
        round_start = time.time()

        logger.info(f"\n{'─' * 40} 第{round_num}轮 ({datetime.now().strftime('%H:%M:%S')}) {'─' * 40}")

        for task_name, task_func in TASKS:
            logger.info(f"[调度器] ▶ {task_name}")
            try:
                has_data = task_func()
                if has_data:
                    round_has_data = True
                    logger.info(f"[调度器] ✓ {task_name} 处理完成")
                else:
                    logger.info(f"[调度器] · {task_name} 无数据")
            except Exception as e:
                logger.error(f"[调度器] ✗ {task_name} 异常: {e}")

            time.sleep(TASK_GAP)

        elapsed = time.time() - round_start
        if not round_has_data:
            logger.info(f"[调度器] 第{round_num}轮 全部无数据（耗时{elapsed:.1f}s），等待{IDLE_WAIT}s...")
            time.sleep(IDLE_WAIT)
        else:
            logger.info(f"[调度器] 第{round_num}轮 完成（耗时{elapsed:.1f}s），继续下一轮")


if __name__ == "__main__":
    run_scheduler()
