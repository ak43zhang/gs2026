import sys
import traceback
import os

log_file = r"F:\pyworkspace2026\gs2026\temp\news_cls_debug.log"

def log(msg):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{msg}]\n")
    print(msg)

log("[INIT] 包装脚本开始")
log(f"[INIT] Python: {sys.executable}")
log(f"[INIT] sys.path: {sys.path}")

try:
    sys.path.insert(0, r"F:\pyworkspace2026\gs2026")
    sys.path.insert(0, r"F:\pyworkspace2026\gs2026\src")
    
    log("[IMPORT] 开始导入 time_task_do_cls")
    from gs2026.analysis.worker.message.deepseek.deepseek_analysis_news_cls import time_task_do_cls
    log("[IMPORT] time_task_do_cls 导入成功")
    
    log("[IMPORT] 开始导入 run_daemon_task")
    from gs2026.utils.task_runner import run_daemon_task
    log("[IMPORT] run_daemon_task 导入成功")
    
    log("[RUN] 准备调用 run_daemon_task")
    log("[RUN] 参数: polling_time=5, year=2026")
    
    # 直接调用，不包装，看具体错误
    run_daemon_task(target=time_task_do_cls, args=(5, "2026"))
    
    log("[RUN] run_daemon_task 调用完成（不应该到这里）")
    
except Exception as e:
    log(f"[ERROR] 异常: {str(e)}")
    log(f"[ERROR] 堆栈:")
    log(traceback.format_exc())
    raise
