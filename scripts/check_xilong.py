import sys
sys.path.insert(0, 'src')
from sqlalchemy import create_engine, text
from gs2026.utils import config_util
import json

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    # 1. 查看西陇科学的数据
    result = conn.execute(text("""
        SELECT stock_code, stock_name, anomaly_time, ai_status, mainline_names,
               ai_analysis
        FROM stock_anomaly 
        WHERE trading_date = '2026-06-24' AND stock_name LIKE '%西陇%'
    """))
    rows = result.fetchall()
    print("=== 西陇科学数据 ===")
    for r in rows:
        print(f"代码: {r[0]}, 名称: {r[1]}, 时间: {r[2]}, 状态: {r[3]}")
        print(f"mainline_names: {r[4]}")
        if r[5]:
            try:
                ai = json.loads(r[5]) if isinstance(r[5], str) else r[5]
                mainline = ai.get('主线归属', '无')
                reason = ai.get('异动原因', '无')
                print(f"异动原因: {reason}")
                print(f"主线归属: {json.dumps(mainline, ensure_ascii=False, indent=2)}")
            except:
                print(f"ai_analysis: {str(r[5])[:200]}")
        print()

    # 2. 查看昨天所有主线
    print("\n=== 昨天所有主线统计 ===")
    result2 = conn.execute(text("""
        SELECT mainline_names FROM stock_anomaly 
        WHERE trading_date = '2026-06-24' AND ai_status = 'done' AND mainline_names IS NOT NULL
    """))
    mainline_count = {}
    for r in result2.fetchall():
        if r[0]:
            try:
                names = json.loads(r[0]) if isinstance(r[0], str) else r[0]
                if isinstance(names, list):
                    for n in names:
                        mainline_count[n] = mainline_count.get(n, 0) + 1
            except:
                pass
    for name, count in sorted(mainline_count.items(), key=lambda x: -x[1]):
        print(f"  {name}: {count}只")
