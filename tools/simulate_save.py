"""
模拟save_buy_point_candidates流程，逐步验证哪里出错
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

# 模拟一条买点候选
test_candidate = {
    'code': '300763',
    'name': 'test_stock',
    'price': 68.50,
    'change_pct': 3.25,
    'cond_net_ratio': True,
    'cond_industry': True,
    'cond_change_pct': False,
    'score': 2
}

test_market_data = {
    'signal': 'warm',
    'passed': 2,
    'total': 3
}

date = '20260519'
time_str = None  # 实时模式

print("=== Step 1: import get_cache ===")
try:
    from gs2026.utils.stock_bond_mapping_cache import get_cache
    cache = get_cache()
    print(f"  cache type: {type(cache)}")
    
    # 测试get方法
    bond_info = cache.get('300763')
    print(f"  cache.get('300763'): {bond_info}")
    
    # 测试get方法是否存在
    if hasattr(cache, 'get'):
        print("  cache.get exists")
    else:
        print("  cache.get DOES NOT EXIST!")
        # 查看可用方法
        print(f"  Available methods: {[m for m in dir(cache) if not m.startswith('_')]}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== Step 2: import _get_shared_engine ===")
try:
    from gs2026.dashboard2.routes.monitor import _get_shared_engine
    engine = _get_shared_engine()
    print(f"  engine: {engine}")
    
    # 测试连接
    from sqlalchemy import text
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print(f"  connection OK: {result.fetchone()}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== Step 3: test data_service.get_bond_data ===")
try:
    from gs2026.dashboard.services.data_service import DataService
    ds = DataService()
    if hasattr(ds, 'get_bond_data'):
        print("  get_bond_data exists")
    else:
        print("  get_bond_data DOES NOT EXIST!")
        print(f"  Available methods: {[m for m in dir(ds) if not m.startswith('_') and callable(getattr(ds, m))]}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== Step 4: simulate full save ===")
try:
    import json
    from sqlalchemy import text
    from datetime import datetime
    
    engine = _get_shared_engine()
    cache = get_cache()
    
    c = test_candidate
    
    # 获取债券信息
    bond_info = cache.get(c.get('code', '')) or {}
    bond_code = bond_info.get('bond_code', '') if isinstance(bond_info, dict) else ''
    print(f"  bond_info for {c['code']}: {bond_info}")
    print(f"  bond_code: {bond_code}")
    
    # 条件
    conditions = [
        {'name': 'net_ratio', 'passed': c.get('cond_net_ratio', False)},
        {'name': 'industry', 'passed': c.get('cond_industry', False)},
        {'name': 'change_pct', 'passed': c.get('cond_change_pct', False)}
    ]
    condition_count = sum(1 for cond in conditions if cond['passed'])
    
    # 等级
    score = c.get('score', 0)
    level = 3 if score >= 3 else (2 if score >= 2 else 1)
    
    market_ctx = {
        'signal': test_market_data.get('signal', '-'),
        'passed': test_market_data.get('passed', 0),
        'total': test_market_data.get('total', 0)
    }
    
    params = {
        'date': date,
        'time': time_str or datetime.now().strftime('%H:%M:%S'),
        'stock_code': c.get('code', ''),
        'stock_name': c.get('name', ''),
        'stock_price': c.get('price'),
        'stock_change_pct': c.get('change_pct'),
        'bond_code': bond_code,
        'bond_price': None,
        'bond_change_pct': None,
        'level': level,
        'condition_count': condition_count,
        'total_conditions': 3,
        'conditions': json.dumps(conditions),
        'market_context': json.dumps(market_ctx)
    }
    
    print(f"  params: {params}")
    
    sql = """
        INSERT INTO buy_point_candidates 
        (date, time, stock_code, stock_name, stock_price, stock_change_pct,
         bond_code, bond_price, bond_change_pct, level, condition_count, total_conditions,
         conditions, market_context)
        VALUES (:date, :time, :stock_code, :stock_name, :stock_price, :stock_change_pct,
         :bond_code, :bond_price, :bond_change_pct, :level, :condition_count, :total_conditions,
         :conditions, :market_context)
    """
    
    with engine.connect() as conn:
        conn.execute(text(sql), params)
        conn.commit()
        print("  INSERT SUCCESS!")
        
        # 验证
        result = conn.execute(text("SELECT COUNT(*) FROM buy_point_candidates WHERE date = '2026-05-19'"))
        count = result.fetchone()[0]
        print(f"  2026-05-19 records: {count}")

except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    traceback.print_exc()
