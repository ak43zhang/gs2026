"""
deepseek_analysis_news_ztb.py 的测试文件
"""
import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gs2026.analysis.worker.message.deepseek.deepseek_analysis_news_ztb import (
    analysis_ztb
)

if __name__ == "__main__":
    import time
    import os
    from gs2026.utils import log_util
    
    start_time = time.time()
    file_name = os.path.basename(__file__)

    # 指定待分析的日期列表
    date_list = ['2020-01-20']
    analysis_ztb(date_list)

    end_time = time.time()
    total_execution_time = end_time - start_time
    logger = log_util.setup_logger(str(Path(__file__).absolute()))
    logger.info(f"----------AI分析总耗时: {total_execution_time} 秒-----------")
