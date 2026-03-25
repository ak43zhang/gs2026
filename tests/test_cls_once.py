"""
测试 time_task_do_cls 的单次执行
"""
import sys
import traceback

sys.path.insert(0, r"F:\pyworkspace2026\gs2026")
sys.path.insert(0, r"F:\pyworkspace2026\gs2026\src")

# 直接导入并执行一次 get_news_cls_analysis
from gs2026.analysis.worker.message.deepseek.deepseek_analysis_news_cls import get_news_cls_analysis

print("[TEST] 调用 get_news_cls_analysis('news_cls2026', 'analysis_news2026', True)...")

try:
    get_news_cls_analysis("news_cls2026", "analysis_news2026", True)
    print("[TEST] 调用完成")
except Exception as e:
    print(f"[ERROR] 异常: {type(e).__name__}: {e}")
    traceback.print_exc()

print("[TEST] 结束")
