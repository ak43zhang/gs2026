import sys
import traceback

# 记录启动日志
with open(r"F:\pyworkspace2026\gs2026\temp\test_news_cls.log", "w", encoding="utf-8") as f:
    f.write("[INFO] 包装脚本开始执行\n")
    f.write(f"[INFO] sys.path = {sys.path}\n")

try:
    sys.path.insert(0, r"F:\pyworkspace2026\gs2026")
    sys.path.insert(0, r"F:\pyworkspace2026\gs2026\src")
    
    with open(r"F:\pyworkspace2026\gs2026\temp\test_news_cls.log", "a", encoding="utf-8") as f:
        f.write("[INFO] 开始导入模块\n")
    
    from gs2026.analysis.worker.message.deepseek.deepseek_analysis_news_cls import time_task_do_cls
    
    with open(r"F:\pyworkspace2026\gs2026\temp\test_news_cls.log", "a", encoding="utf-8") as f:
        f.write("[INFO] time_task_do_cls 导入成功\n")
    
    from gs2026.utils.task_runner import run_daemon_task
    
    with open(r"F:\pyworkspace2026\gs2026\temp\test_news_cls.log", "a", encoding="utf-8") as f:
        f.write("[INFO] run_daemon_task 导入成功\n")
        f.write("[INFO] 准备启动 run_daemon_task\n")
    
    # 启动（使用较短的轮询时间便于测试）
    run_daemon_task(target=time_task_do_cls, args=(5, "2026"))
    
    with open(r"F:\pyworkspace2026\gs2026\temp\test_news_cls.log", "a", encoding="utf-8") as f:
        f.write("[INFO] run_daemon_task 调用完成\n")
        
except Exception as e:
    with open(r"F:\pyworkspace2026\gs2026\temp\test_news_cls.log", "a", encoding="utf-8") as f:
        f.write(f"[ERROR] 异常: {str(e)}\n")
        f.write(f"[ERROR] 堆栈: {traceback.format_exc()}\n")
    raise
