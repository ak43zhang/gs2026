import sys
sys.path.insert(0, 'src')
from sqlalchemy import create_engine, text
from gs2026.utils import config_util
import json

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    result = conn.execute(text(
        "SELECT stock_code, stock_name, mainline_names, ai_analysis "
        "FROM stock_anomaly "
        "WHERE trading_date = '2026-06-25' AND ai_status = 'done'"
    ))
    rows = result.fetchall()

    total = len(rows)
    mismatch = 0
    examples = []

    for r in rows:
        code, name, ml_names, ai_raw = r
        ml_list = []
        if ml_names:
            try:
                ml_list = json.loads(ml_names) if isinstance(ml_names, str) else (ml_names if isinstance(ml_names, list) else [])
            except:
                pass

        ai_mainlines = None
        if ai_raw:
            try:
                ai = json.loads(ai_raw) if isinstance(ai_raw, str) else ai_raw
                ai_mainlines = ai.get('主线归属')
            except:
                pass

        has_ml = len(ml_list) > 0 and ml_list != ['独立个股']
        has_ai = isinstance(ai_mainlines, list) and len(ai_mainlines) > 0

        if has_ml and not has_ai:
            mismatch += 1
            if len(examples) < 5:
                examples.append(f'  {code} {name}: mainline_names={ml_list}')

    print(f'2026-06-25 done: {total} 只')
    pct = mismatch * 100 // total if total else 0
    print(f'有 mainline_names 但无 ai_analysis[主线归属]: {mismatch} 只 ({pct}%)')
    if examples:
        print('示例:')
        for e in examples:
            print(e)
    else:
        print('✅ 无不一致数据')
