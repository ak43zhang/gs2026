"""
直接测试 time_task_do_cls 函数
"""
import sys
sys.path.insert(0, r"F:\pyworkspace2026\gs2026")
sys.path.insert(0, r"F:\pyworkspace2026\gs2026\src")

from gs2026.analysis.worker.message.deepseek.deepseek_analysis_news_cls import time_task_do_cls

print("直接调用 time_task_do_cls(5, '2026')...")
print("（按 Ctrl+C 停止）")

try:
    time_task_do_cls(5, "2026")
except Exception as e:
    print(f"异常: {e}")
    import traceback
    traceback.print_exc()
