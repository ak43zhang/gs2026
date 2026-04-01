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
    # 测试债券排行 API
    resp = client.get('/api/monitor/attack-ranking/bond?date=20260401&time=10:25:27&limit=15')
    print('状态码:', resp.status_code)
    
    import json
    data = json.loads(resp.data)
    print('成功:', data.get('success'))
    print('数据条数:', len(data.get('data', [])))
    
    if data.get('data'):
        print('\n第一条数据:')
        print(json.dumps(data['data'][0], indent=2, ensure_ascii=False))
        
        # 检查是否有涨跌幅和行业
        item = data['data'][0]
        print('\n字段检查:')
        print('  change_pct:', item.get('change_pct', 'MISSING'))
        print('  industry_name:', item.get('industry_name', 'MISSING'))
