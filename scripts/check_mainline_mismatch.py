import sys
sys.path.insert(0, 'src')
from sqlalchemy import create_engine, text
from gs2026.utils import config_util
import json

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT stock_code, stock_name, mainline_names, ai_analysis
        FROM stock_anomaly 
        WHERE trading_date = '2026-06-24' AND ai_status = 'done'
    """))
    rows = result.fetchall()
    
    mismatch = []
    no_mainline_attr = []
    
    for r in rows:
        code, name, ml_names, ai_raw = r
        # 解析 mainline_names
        ml_list = []
        if ml_names:
            try:
                ml_list = json.loads(ml_names) if isinstance(ml_names, str) else ml_names
            except:
                pass
        
        # 解析 ai_analysis['主线归属']
        ai_mainlines = None
        if ai_raw:
            try:
                ai = json.loads(ai_raw) if isinstance(ai_raw, str) else ai_raw
                ai_mainlines = ai.get('主线归属')
            except:
                pass
        
        # 检查不一致
        has_ml_names = len(ml_list) > 0 and ml_list != ['独立个股']
        has_ai_mainlines = isinstance(ai_mainlines, list) and len(ai_mainlines) > 0
        
        if has_ml_names and not has_ai_mainlines:
            mismatch.append((code, name, ml_list, ai_mainlines))
        
        if not has_ai_mainlines and ai_mainlines is not None:
            no_mainline_attr.append((code, name, ml_list, ai_mainlines))
    
    print(f"总计 done 状态: {len(rows)} 只")
    print(f"\n=== 有 mainline_names 但无有效 ai_analysis['主线归属'] 的股票: {len(mismatch)} 只 ===")
    for code, name, ml, ai_ml in mismatch[:20]:
        print(f"  {code} {name}: mainline_names={ml}, ai['主线归属']={ai_ml}")
    
    print(f"\n=== ai_analysis['主线归属'] 非数组的股票: {len(no_mainline_attr)} 只 ===")
    for code, name, ml, ai_ml in no_mainline_attr[:10]:
        print(f"  {code} {name}: ai['主线归属']={ai_ml}")
