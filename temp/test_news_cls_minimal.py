import sys
import time
import traceback
from pathlib import Path

log_dir = Path(r"F:/pyworkspace2026/gs2026") / "logs" / "analysis"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "news_cls_minimal.log"

def log(msg):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{msg}]\n")
    print(msg, flush=True)

log("=" * 60)
log("最小化测试 time_task_do_cls")

sys.path.insert(0, r"F:/pyworkspace2026/gs2026")
sys.path.insert(0, r"F:/pyworkspace2026/gs2026/src")

try:
    log("[1] 导入模块...")
    import pandas as pd
    from gs2026.utils import config_util
    from sqlalchemy import create_engine
    
    log("[2] 获取数据库配置...")
    url = config_util.get_config('common.url')
    engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
    
    year = "2026"
    table_name = "news_cls" + year
    analysis_table_name = "analysis_news" + year
    
    log(f"[3] 表名: {table_name}, {analysis_table_name}")
    
    iteration = 0
    while True:
        iteration += 1
        log(f"[4.{iteration}] 开始第 {iteration} 轮...")
        
        with engine.connect() as conn:
            sql = f"select SQL_NO_CACHE `内容hash`,`内容` from {table_name} where (analysis is null or analysis='') order by SUBSTRINg(`发布时间`,1,7) desc,rand() limit 60"
            df = pd.read_sql(sql, con=conn)
            lists = df.values.tolist()
            log(f"[4.{iteration}] 数据量: {len(lists)}")
            
            if len(lists) < 5:
                log(f"[4.{iteration}] 数据量小于5，休眠10分钟...")
                time.sleep(10)  # 测试时用10秒代替600秒
                log(f"[4.{iteration}] 休眠结束，继续循环")
            elif len(lists) < 20:
                log(f"[4.{iteration}] 数据量 {len(lists)}，需要分析（但测试时跳过）")
                time.sleep(10)
            else:
                log(f"[4.{iteration}] 数据量 {len(lists)}，需要分析（但测试时跳过）")
                time.sleep(10)
        
        if iteration >= 3:
            log("[5] 完成3轮测试，退出")
            break
    
    log("[EXIT] 正常完成")
    
except Exception as e:
    log(f"[ERROR] {type(e).__name__}: {str(e)}")
    log(traceback.format_exc())
