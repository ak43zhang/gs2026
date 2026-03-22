"""
combine_collection.py 的测试文件
"""
import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gs2026.analysis.worker.message.deepseek.combine_collection import (
    time,
    os,
    datetime,
    main_collection_pipeline,
    email_util,
    con,
    logger,
)

if __name__ == "__main__":
    start_deal_time: float = time.time()
    file_name: str = os.path.basename(__file__)

    try:
        # 设定采集基准日期
        base_date: datetime = datetime(2026, 3, 20)

        # 执行主采集流水线
        success: bool = main_collection_pipeline(base_date)

        if success:
            logger.info("采集流程成功完成")

    except KeyboardInterrupt:
        # 用户手动中断时发送告警邮件
        logger.warning("任务被用户中断")
        ERROR_TITLE: str = "异常告警"
        ERROR_CONTENT: str = f"{file_name} 异常退出"
        FULL_HTML: str = email_util.full_html_fun(ERROR_TITLE, ERROR_CONTENT)
        for receiver_email in email_util.get_email_list():
            email_util.email_send_html(receiver_email, "异常告警", FULL_HTML)
        logger.warning("任务已终止")

    except Exception as e:
        # 未预期异常时发送告警邮件并重新抛出
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
        logger.info("数据库连接已关闭")

    end_deal_time: float = time.time()
    total_execution_time: float = end_deal_time - start_deal_time
    logger.info(f"采集总耗时: {total_execution_time:.2f} 秒")
    logger.info(f"----------AI分析总耗时: {total_execution_time} 秒-----------")
