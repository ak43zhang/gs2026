import sys
import traceback
import os
from pathlib import Path

# 确保路径设置正确（必须在导入其他模块之前）
PROJECT_ROOT = r"F:/pyworkspace2026/gs2026"
SRC_PATH = os.path.join(PROJECT_ROOT, "src")

# 清除可能冲突的路径，确保 src 在最前面
if PROJECT_ROOT in sys.path:
    sys.path.remove(PROJECT_ROOT)
if SRC_PATH in sys.path:
    sys.path.remove(SRC_PATH)

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SRC_PATH)

# 创建日志目录
log_dir = Path(PROJECT_ROOT) / "logs" / "analysis"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "news_combine.log"

def log(msg):
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{msg}]\n")
    except:
        pass

log("=" * 60)
log(f"[INIT] 启动 news_combine")
log(f"[INIT] PROJECT_ROOT: {PROJECT_ROOT}")
log(f"[INIT] SRC_PATH: {SRC_PATH}")
log(f"[INIT] sys.path[0:2]: {sys.path[0:2]}")

try:
    from gs2026.analysis.worker.message.deepseek.deepseek_analysis_news_combine import time_task_do_combine
    from gs2026.utils.task_runner import run_daemon_task
    log("[RUN] 调用 run_daemon_task")
    # 使用 daemon=False 前台运行，防止进程退出
    run_daemon_task(target=time_task_do_combine, args=(10,), daemon=False)
    log("[EXIT] 正常退出")
except Exception as e:
    log(f"[ERROR] {type(e).__name__}: {str(e)}")
    log(traceback.format_exc())
    raise
