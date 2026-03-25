"""
直接测试 time_task_do_cls，捕获所有异常
"""
import sys
import traceback

sys.path.insert(0, r"F:\pyworkspace2026\gs2026")
sys.path.insert(0, r"F:\pyworkspace2026\gs2026\src")

try:
    print("[TEST] 导入 time_task_do_cls...")
    from gs2026.analysis.worker.message.deepseek.deepseek_analysis_news_cls import time_task_do_cls
    print("[TEST] 导入成功")
    
    print("[TEST] 直接调用 time_task_do_cls(5, '2026')...")
    time_task_do_cls(5, "2026")
    
except Exception as e:
    print(f"[ERROR] 异常类型: {type(e).__name__}")
    print(f"[ERROR] 异常信息: {e}")
    print("[ERROR] 完整堆栈:")
    traceback.print_exc()

print("[TEST] 结束")
