"""
deepseek_analysis_notice.py 的测试文件
"""
import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gs2026.analysis.worker.message.deepseek.deepseek_analysis_notice import (
    timer_task_do_notice
)

if __name__ == "__main__":
    import time
    import os
    from gs2026.utils import log_util, email_util
    
    start_deal_time = time.time()
    file_name = os.path.basename(__file__)

    # 主线程保持运行，执行公告分析轮询任务
    try:
        timer_task_do_notice(1)
    except Exception as e:
        logger = log_util.setup_logger(str(Path(__file__).absolute()))
        logger.exception(f"采集流程失败: {e}")
        # 构建异常告警邮件并发送给所有配置的接收人
        ERROR_TITLE = "异常告警"
        ERROR_CONTENT = f"{file_name} 执行异常: {str(e)}"
        FULL_HTML = email_util.full_html_fun(ERROR_TITLE, ERROR_CONTENT)
        for receiver_email in email_util.get_email_list():
            email_util.email_send_html(receiver_email, "异常告警", FULL_HTML)
        raise
    finally:
        # 确保数据库事务提交并关闭连接
        from gs2026.analysis.worker.message.deepseek.deepseek_analysis_notice import con
        con.commit()
        con.close()

    end_deal_time = time.time()
    total_execution_time = end_deal_time - start_deal_time
    logger = log_util.setup_logger(str(Path(__file__).absolute()))
    logger.info(f"----------AI分析总耗时: {total_execution_time} 秒-----------")
