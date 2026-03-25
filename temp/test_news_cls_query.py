import sys
import traceback
from pathlib import Path

log_dir = Path(r"F:/pyworkspace2026/gs2026") / "logs" / "analysis"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "news_cls_query.log"

def log(msg):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{msg}]\n")
    print(msg)

sys.path.insert(0, r"F:/pyworkspace2026/gs2026")
sys.path.insert(0, r"F:/pyworkspace2026/gs2026/src")

try:
    log("[INIT] 测试数据库查询")
    
    # 只导入必要的模块
    import pandas as pd
    from gs2026.utils import config_util
    from sqlalchemy import create_engine
    
    log("[DB] 获取配置...")
    url = config_util.get_config('common.url')
    log(f"[DB] URL: {url[:30]}...")
    
    log("[DB] 创建引擎...")
    engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
    
    log("[DB] 连接数据库...")
    with engine.connect() as conn:
        log("[DB] 查询 news_cls2026...")
        sql = "select SQL_NO_CACHE `内容hash`,`内容` from news_cls2026 where (analysis is null or analysis='') order by SUBSTRINg(`发布时间`,1,7) desc,rand() limit 60"
        
        log(f"[DB] SQL: {sql[:80]}...")
        df = pd.read_sql(sql, con=conn)
        log(f"[DB] 查询完成，数据量: {len(df)}")
        
        if len(df) > 0:
            log(f"[DB] 第一条数据: {df.iloc[0].tolist()[:2]}")
        else:
            log("[DB] 没有数据需要分析")
    
    log("[EXIT] 正常完成")
    
except Exception as e:
    log(f"[ERROR] {type(e).__name__}: {str(e)}")
    log(traceback.format_exc())
