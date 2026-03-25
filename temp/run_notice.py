import sys
import traceback
import os
from pathlib import Path

# 创建日志目录
log_dir = Path(r"F:\\pyworkspace2026\\gs2026") / "logs" / "analysis"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "notice.log"

def log(msg):
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{msg}]\n")
    except:
        pass

sys.path.insert(0, r"F:\\pyworkspace2026\\gs2026")
sys.path.insert(0, r"F:\\pyworkspace2026\\gs2026\src")

try:
    log("[INIT] 启动 notice")
    from gs2026.analysis.worker.message.deepseek.deepseek_analysis_notice import timer_task_do_notice
    from gs2026.utils.task_runner import run_daemon_task
    log("[RUN] 调用 run_daemon_task")
    # 使用 daemon=False 前台运行，防止进程退出
    run_daemon_task(target=timer_task_do_notice, args=(1,), daemon=False)
    log("[EXIT] 正常退出")
except Exception as e:
    log(f"[ERROR] {str(e)}")
    log(traceback.format_exc())
    raise
