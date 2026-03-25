"""
完整测试：使用 run_daemon_task 启动财联社分析
"""
import sys
sys.path.insert(0, r"F:\pyworkspace2026\gs2026")
sys.path.insert(0, r"F:\pyworkspace2026\gs2026\src")

import traceback
from gs2026.analysis.worker.message.deepseek.deepseek_analysis_news_cls import time_task_do_cls
from gs2026.utils.task_runner import run_daemon_task

print("[TEST] 开始测试")
print("[TEST] 使用 run_daemon_task 启动 time_task_do_cls")

try:
    # 使用 daemon=False 前台运行，这样能看到输出
    run_daemon_task(target=time_task_do_cls, args=(5, "2026"), daemon=False)
except Exception as e:
    print(f"[ERROR] 异常: {e}")
    traceback.print_exc()

print("[TEST] 测试结束")
