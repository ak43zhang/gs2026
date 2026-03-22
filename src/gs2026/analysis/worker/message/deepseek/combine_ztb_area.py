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


if __name__ == "__main__":
    start_time: float = time.time()
    file_name: str = os.path.basename(__file__)

    try:
        # 设定分析基准日期
        base_date: datetime = datetime(2026, 3, 20)
        next_date: datetime = base_date + timedelta(days=1)

        # 构建待分析的日期列表（当前仅包含基准日期）
        date_list: list[str] = [base_date.strftime('%Y-%m-%d')]

        # ---- 任务1: 涨停板新闻分析 ----
        # 设定触发时间为当日 18:00，等待数据采集完成后再开始分析
        target_time_ztb_collect: datetime = base_date.replace(hour=18, minute=0, second=0)
        deepseek_analysis_event_driven.check_time_and_execute(
            target_date=target_time_ztb_collect,
            check_interval=60,
            execute_func=deepseek_analysis_news_ztb.analysis_ztb,
            date_list_=date_list
        )

        # ---- 任务2: 区域事件驱动分析 ----
        # 设定触发时间为次日 00:00，确保当日所有数据已完成采集和入库
        target_time_area: datetime = next_date.replace(hour=0, minute=0, second=0)
        deepseek_analysis_event_driven.check_time_and_execute(
            target_date=target_time_area,
            check_interval=60,
            execute_func=deepseek_analysis_event_driven.analysis_event_driven,
            date_list_=date_list
        )

        # ---- 任务3: 公告风险定时扫描 ----
        # 执行公告风险扫描定时任务，参数 1 表示扫描周期/模式
        deepseek_analysis_notice.timer_task_do_notice(1)

    except Exception as e:
        # 分析流程异常时记录日志并发送告警邮件
        logger.exception(f"采集流程失败: {e}")
        ERROR_TITLE: str = "异常告警"
        ERROR_CONTENT: str = f"{file_name} 执行异常: {str(e)}"
        FULL_HTML: str = email_util.full_html_fun(ERROR_TITLE, ERROR_CONTENT)
        for receiver_email in email_util.get_email_list():
            email_util.email_send_html(receiver_email, "异常告警", FULL_HTML)
        raise

    finally:
        # 确保数据库连接正确提交并释放
        con.commit()
        con.close()

    end_time: float = time.time()
    total_execution_time: float = end_time - start_time
    logger.info(f"----------AI分析总耗时: {total_execution_time} 秒-----------")
