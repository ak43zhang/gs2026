"""
测试 deepseek_analysis 函数
"""
import sys
import traceback

sys.path.insert(0, r"F:\pyworkspace2026\gs2026")
sys.path.insert(0, r"F:\pyworkspace2026\gs2026\src")

try:
    print("[TEST] 导入 deepseek_analysis...")
    from gs2026.analysis.worker.message.deepseek.deepseek_analysis_event_driven import deepseek_analysis
    print("[TEST] 导入成功")
    
    print("[TEST] 调用 deepseek_analysis('测试', True)...")
    result = deepseek_analysis("测试", True)
    print(f"[TEST] 结果: {result}")
    
except Exception as e:
    print(f"[ERROR] {type(e).__name__}: {e}")
    traceback.print_exc()

print("[TEST] 结束")
