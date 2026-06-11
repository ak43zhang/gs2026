import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py', encoding='utf-8') as f:
    content = f.read()

# Insert before _mark_and_sort_realtime_attacks
marker = 'def _mark_and_sort_realtime_attacks(bonds: list, date: str, time_str: str = None) -> list:'
if marker in content:
    new_func = '''def _mark_stock_tick_up(stocks: list, date: str) -> list:
    \"\"\"
    标记3秒时间区间内的股票实时上攻数据（tick上涨）
    
    Args:
        stocks: 股票数据列表
        date: 日期 YYYYMMDD
    
    Returns:
        标记后的股票数据列表
    \"\"\"
    if not stocks:
        return stocks
    
    try:
        from gs2026.utils import redis_util
        from datetime import datetime, timedelta
        from gs2026.utils.mysql_util import MysqlTool
        import pandas as pd
        
        client = redis_util._get_redis_client()
        
        # 获取当前时间
        query_time = datetime.now().strftime('%H:%M:%S')
        
        # 计算3秒时间区间
        query_dt = datetime.strptime(f"{date} {query_time}", "%Y%m%d %H:%M:%S")
        start_time = (query_dt - timedelta(seconds=3)).strftime("%H:%M:%S")
        end_time = query_time
        
        # 从MySQL查询3秒区间内的股票
        realtime_codes = set()
        
        try:
            table_name = f"monitor_gp_apqd_{date}"
            
            query = f"SELECT DISTINCT code FROM {table_name} WHERE time >= '{start_time}' AND time <= '{end_time}'"
            
            mysql_tool = MysqlTool()
            with mysql_tool.engine.connect() as conn:
                df = pd.read_sql(query, conn)
                if not df.empty:
                    realtime_codes = set(df['code'].astype(str).tolist())
                    
        except Exception as e:
            pass  # 查询失败不影响主功能
        
        # 标记tick上涨
        for stock in stocks:
            code = str(stock.get('code', ''))
            stock['is_tick_up'] = code in realtime_codes
            
        return stocks
        
    except Exception as e:
        # 标记失败不影响主功能
        for stock in stocks:
            stock['is_tick_up'] = False
        return stocks


''' + marker
    
    content = content.replace(marker, new_func)
    with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Function added successfully')
else:
    print('Marker not found')
