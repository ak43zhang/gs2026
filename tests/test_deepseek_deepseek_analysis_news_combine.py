"""
deepseek_analysis_news_combine.py 的测试文件
"""
import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gs2026.analysis.worker.message.deepseek.deepseek_analysis_news_combine import (
    run_daemon_task,
    time_task_do_combine,
)

if __name__ == "__main__":
    run_daemon_task(target=time_task_do_combine, args=(3, '2026'))
