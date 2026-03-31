"""调度分析模块——涨停板与区域分析的并发执行入口。

本模块负责调度涨停板新闻分析、区域事件驱动分析和公告定时任务，
各分析任务通过事件驱动机制在指定时间点触发执行，支持并发调度。

核心功能:
    - 涨停板新闻分析：在当日 18:00 后触发，对涨停板数据进行 DeepSeek AI 分析
    - 区域事件驱动分析：在次日 00:00 后触发，执行区域维度的事件驱动分析
    - 公告风险定时任务：周期性执行公告风险扫描

依赖关系:
    - gs2026.analysis.worker.message.deepseek: DeepSeek 分析引擎（事件驱动、涨停板、公告）
    - gs2026.utils: 配置工具、数据库工具、邮件工具、日志工具等基础设施
    - SQLAlchemy: 数据库连接管理
"""
import os
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning

from gs2026.utils import mysql_util, config_util, email_util, log_util, pandas_display_config

from gs2026.analysis.worker.message.deepseek import (deepseek_analysis_event_driven,
                                                     deepseek_analysis_news_ztb,
                                                     deepseek_analysis_notice)
from gs2026.utils.task_runner import run_daemon_task

# 忽略 SQLAlchemy 的反射警告，避免日志噪音
warnings.filterwarnings("ignore", category=SAWarning)

# 初始化模块级日志记录器（以当前文件路径作为 logger 名称）
logger = log_util.setup_logger(str(Path(__file__).absolute()))
# 设置 pandas 全局显示配置
pandas_display_config.set_pandas_display_options()

# 从配置文件读取数据库连接 URL
url: str = config_util.get_config("common.url")

# 初始化数据库连接引擎，启用连接池回收和预检机制
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()
# 初始化 MySQL 工具和邮件工具实例
mysql_util = mysql_util.MysqlTool(url)
email_util = email_util.EmailUtil()

def main_collection_pipeline(base_date: datetime) -> bool:

    next_date = base_date + timedelta(days=1)

    date_list = [base_date.strftime('%Y-%m-%d')]

    # 调度采集涨停板数据
    target_time_ztb_collect = base_date.replace(hour=18, minute=0, second=0)
    deepseek_analysis_event_driven.check_time_and_execute(
        target_date=target_time_ztb_collect,
        check_interval=60,
        execute_func=deepseek_analysis_news_ztb.analysis_ztb,
        date_list_=date_list
    )

    # 分析area
    target_time_area = next_date.replace(hour=0, minute=0, second=0)
    deepseek_analysis_event_driven.check_time_and_execute(
        target_date=target_time_area,
        check_interval=60,
        execute_func=deepseek_analysis_event_driven.analysis_event_driven,
        date_list_=date_list
    )

    deepseek_analysis_notice.timer_task_do_notice(1)




if __name__ == "__main__":
    # 从环境变量读取日期参数（格式: gs2026_combine_ztb_area_date）
    date_str = os.environ.get('gs2026_combine_ztb_area_date')

    if date_str:
        # 使用指定日期
        base_date = datetime.strptime(date_str, '%Y%m%d')
        logger.info(f"使用指定日期: {base_date.strftime('%Y-%m-%d')}")
    else:
        # 使用默认日期（今天）
        base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        logger.info(f"使用默认日期(今天): {base_date.strftime('%Y-%m-%d')}")

    run_daemon_task(target=main_collection_pipeline, args=(base_date,))
