import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard2.routes.monitor import get_bond_ranking
from flask import Flask, request
import json

app = Flask(__name__)

with app.test_request_context('/api/monitor/attack-ranking/bond?date=20260518&limit=5'):
    response = get_bond_ranking()
    data = json.loads(response.data)
    if data.get('success') and data.get('data'):
        for item in data['data'][:3]:
            print(f"Code: {item.get('code')}, Price: {item.get('price')}, Change: {item.get('change_pct')}")
    else:
        print(f"Error: {data}")
