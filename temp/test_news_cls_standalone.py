"""
完全独立的测试，不导入任何 deepseek 模块
"""
import sys
import time
import traceback
from pathlib import Path

log_dir = Path(r"F:/pyworkspace2026/gs2026") / "logs" / "analysis"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "news_cls_standalone.log"

def log(msg):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{msg}]\n")
    print(msg, flush=True)

log("=" * 60)
log("完全独立测试")

sys.path.insert(0, r"F:/pyworkspace2026/gs2026")
sys.path.insert(0, r"F:/pyworkspace2026/gs2026/src")

try:
    log("[1] 只导入基础模块...")
    import pandas as pd
    from gs2026.utils import config_util
    from sqlalchemy import create_engine
    
    log("[2] 模拟 time_task_do_cls 逻辑...")
    url = config_util.get_config('common.url')
    engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
    
    year = "2026"
    table_name = "news_cls" + year
    
    iteration = 0
    while True:
        iteration += 1
        log(f"[3.{iteration}] 第 {iteration} 轮")
        
        with engine.connect() as conn:
            from sqlalchemy import text
            sql = f"select count(*) from {table_name}"
            result = conn.execute(text(sql))
            count = result.fetchone()[0]
            log(f"[3.{iteration}] 表 {table_name} 总行数: {count}")
        
        log(f"[3.{iteration}] 休眠5秒...")
        time.sleep(5)
        log(f"[3.{iteration}] 休眠结束")
        
        if iteration >= 5:
            log("[4] 完成5轮，正常退出")
            break
    
    log("[EXIT] 正常完成")
    
except Exception as e:
    log(f"[ERROR] {type(e).__name__}: {str(e)}")
    log(traceback.format_exc())
