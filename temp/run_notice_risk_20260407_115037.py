#!/usr/bin/env python3
import sys
import os
from pathlib import Path

# 重定向输出到空设备
if sys.platform == "win32":
    sys.stdout = open(os.devnull, "w")
    sys.stderr = open(os.devnull, "w")

# 计算项目根目录（包装脚本在 temp/ 目录，需要向上3层到 gs2026 目录）
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import traceback
from datetime import datetime

SERVICE_ID = "notice_risk"
FUNCTION_NAME = "notice_and_risk_collect"

def log(msg):
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_dir = PROJECT_ROOT / "logs" / "collection"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / (SERVICE_ID + ".log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write("[" + ts + "] " + str(msg) + chr(10))
    except:
        pass

log("=" * 60)
log("[INIT] 启动 " + SERVICE_ID)
log("[INIT] 函数: " + FUNCTION_NAME)

try:
    from src.gs2026.collection.risk.notice_risk_history import notice_and_risk_collect
    log("[RUN] 调用 " + FUNCTION_NAME)
    notice_and_risk_collect(start_date='2026-04-07', end_date='2026-04-07')
    log("[EXIT] 正常退出")
except Exception as e:
    log("[ERROR] " + str(type(e).__name__) + ": " + str(e))
    log(traceback.format_exc())
    raise
