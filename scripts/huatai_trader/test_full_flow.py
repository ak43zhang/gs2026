"""验证全流程：MySQL方案加载 → 适配器 → HTTP → 华泰填充"""
import sys
sys.path.insert(0, 'src')
import warnings
warnings.filterwarnings('ignore')
import json

# 1. 模拟加载方案（和monitor_bond一样从MySQL读）
from gs2026.utils import config_util, mysql_util
from sqlalchemy import text

url = config_util.get_config('common.url')
url = url.replace('charset=utf8', 'charset=utf8mb4')
engine = mysql_util.MysqlTool(url).engine

with engine.connect() as conn:
    result = conn.execute(text('''
        SELECT scheme_name, conditions_json, stop_loss_pct, take_profit_pct,
               max_hold_time, price_offset, offset_mode
        FROM quant_screen_schemes
        WHERE is_active = 1 AND use_realtime = 1
    '''))
    schemes = []
    for row in result:
        schemes.append({
            'name': row.scheme_name,
            'conditions': json.loads(row.conditions_json) if row.conditions_json else [],
            'stop_loss': float(row.stop_loss_pct) if row.stop_loss_pct else 3.0,
            'take_profit': float(row.take_profit_pct) if row.take_profit_pct else 5.0,
            'max_hold_time': row.max_hold_time,
            'price_offset': float(row.price_offset) if row.price_offset else 0.0,
            'offset_mode': row.offset_mode or 'fixed',
        })

print(f'[1] MySQL方案加载: {len(schemes)}个')
for s in schemes:
    print(f'    - {s["name"]}')

# 2. 加载trader_adapter
from gs2026.monitor.trader_adapter import on_hit, get_adapter

TRADER_CONFIG = {
    'enabled': True,
    'check_trading_time': False,  # 测试时关闭时段检查
    'trader_api_url': 'http://127.0.0.1:8081',
    'allowed_schemes': [],
    'blocked_schemes': [],
    'min_interval_seconds': 10,
    'max_daily_triggers': 50,
    'default_lots': 1,
    'request_timeout': 5,
    'price_range': {'min': 50, 'max': 200},
    'notifications': {'sound': True, 'console': True, 'windows_toast': False},
}
adapter = get_adapter(TRADER_CONFIG)
print(f'[2] 适配器加载完成')

# 3. 模拟一个命中
test_code = '123257'
test_name = '美诺转债'
test_scheme = schemes[0]['name'] if schemes else '基础稳定胜率'

print(f'[3] 模拟命中: {test_code} {test_name} 方案={test_scheme}')
print(f'    调用 trader_on_hit...')

result = on_hit(test_code, test_name, scheme_name=test_scheme)
print(f'[4] 触发结果: {result}')
if result:
    print(f'    ✓ 全流程通过！华泰软件应已填充代码 {test_code}')
else:
    status = adapter.get_status()
    print(f'    适配器状态: {status}')
