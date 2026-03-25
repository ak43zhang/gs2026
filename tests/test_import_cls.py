"""
测试模块导入是否会因为数据库连接失败而抛异常
"""
import sys
sys.path.insert(0, r"F:\pyworkspace2026\gs2026")
sys.path.insert(0, r"F:\pyworkspace2026\gs2026\src")

try:
    print("[TEST] 开始导入 deepseek_analysis_news_cls 模块...")
    import gs2026.analysis.worker.message.deepseek.deepseek_analysis_news_cls as mod
    print("[TEST] 模块导入成功")
    print(f"[TEST] engine: {mod.engine}")
    print(f"[TEST] con: {mod.con}")
except Exception as e:
    print(f"[ERROR] 导入失败: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
