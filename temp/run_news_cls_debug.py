import sys
import traceback
import os
from pathlib import Path
import datetime

# 创建日志目录
log_dir = Path(r"F:\pyworkspace2026\gs2026") / "logs" / "analysis"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "news_cls_debug.log"

def log(msg):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{timestamp}] {msg}"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{line}\n")
        print(line)
    except Exception as e:
        print(f"[LOG ERROR] {e}: {line}")

log("=" * 60)
log("[INIT] 启动 news_cls 调试版本")
log(f"[INIT] Python: {sys.executable}")
log(f"[INIT] CWD: {os.getcwd()}")
log(f"[INIT] sys.path before: {sys.path[:3]}")

sys.path.insert(0, r"F:\pyworkspace2026\gs2026")
sys.path.insert(0, r"F:\pyworkspace2026\gs2026\src")

log(f"[INIT] sys.path after: {sys.path[:3]}")

try:
    log("[IMPORT] 开始导入 time_task_do_cls...")
    from gs2026.analysis.worker.message.deepseek.deepseek_analysis_news_cls import time_task_do_cls
    log("[IMPORT] time_task_do_cls 导入成功")
    
    log("[IMPORT] 开始导入 run_daemon_task...")
    from gs2026.utils.task_runner import run_daemon_task
    log("[IMPORT] run_daemon_task 导入成功")
    
    log("[RUN] 准备调用 time_task_do_cls(10, '2026')...")
    # 直接调用，不使用 run_daemon_task，看具体错误
    time_task_do_cls(10, "2026")
    
except Exception as e:
    log(f"[ERROR] {type(e).__name__}: {str(e)}")
    log("[ERROR] 堆栈:")
    for line in traceback.format_exc().split("\n"):
        log(f"  {line}")
    raise

log("[EXIT] 正常结束")
