#!/usr/bin/env python3
"""测试债券排行API"""

import sys
sys.path.insert(0, 'src')

from flask import Flask
from gs2026.dashboard2.routes.monitor import monitor_bp

app = Flask(__name__)
app.register_blueprint(monitor_bp, url_prefix='/api/monitor')

# 模拟请求
with app.test_client() as client:
    print("=== 测试债券排行API ===")
    
    # 测试有时间参数
    resp = client.get('/api/monitor/attack-ranking/bond?date=20260401&time=10:25:27&limit=15')
    import json
    data = json.loads(resp.data)
    
    print(f"状态码: {resp.status_code}")
    print(f"成功: {data.get('success')}")
    print(f"数据条数: {len(data.get('data', []))}")
    
    if data.get('data'):
        item = data['data'][0]
        print(f"\n第一条数据:")
        print(f"  code: {item.get('code')}")
        print(f"  name: {item.get('name')}")
        print(f"  change_pct: {item.get('change_pct')} (类型: {type(item.get('change_pct')).__name__})")
        print(f"  industry_name: {item.get('industry_name')}")
