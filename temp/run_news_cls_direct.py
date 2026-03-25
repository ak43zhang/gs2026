import sys
import traceback
from pathlib import Path

log_dir = Path(r"F:/pyworkspace2026/gs2026") / "logs" / "analysis"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "news_cls_direct.log"

def log(msg):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{msg}]\n")
    print(msg)

sys.path.insert(0, r"F:/pyworkspace2026/gs2026")
sys.path.insert(0, r"F:/pyworkspace2026/gs2026/src")

try:
    log("[INIT] 直接启动 time_task_do_cls")
    from gs2026.analysis.worker.message.deepseek.deepseek_analysis_news_cls import time_task_do_cls
    log("[RUN] 直接调用 time_task_do_cls(10, '2026')...")
    time_task_do_cls(10, "2026")
    log("[EXIT] 正常退出")
except Exception as e:
    log(f"[ERROR] {type(e).__name__}: {str(e)}")
    log(traceback.format_exc())
    raise
