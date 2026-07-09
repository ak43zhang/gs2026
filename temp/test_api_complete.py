#!/usr/bin/env python3
"""
测试 /api/quant-schemes API 是否正常工作
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import requests
import json

API_BASE = 'http://localhost:8080/api'

def test_get_schemes():
    """测试获取方案列表"""
    print("=" * 60)
    print("测试1: GET /api/quant-schemes")
    print("=" * 60)
    
    try:
        response = requests.get(f'{API_BASE}/quant-schemes?scene=backtest', timeout=5)
        print(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"成功: {data.get('success')}")
            schemes = data.get('schemes', [])
            print(f"方案数量: {len(schemes)}")
            
            for s in schemes:
                status = "在用" if s.get('is_active') else "停用"
                print(f"  - {s.get('scheme_name')} [{status}]")
            return True
        else:
            print(f"错误: {response.text}")
            return False
    except Exception as e:
        print(f"请求失败: {e}")
        return False

def test_save_scheme():
    """测试保存方案"""
    print("\n" + "=" * 60)
    print("测试2: POST /api/quant-schemes")
    print("=" * 60)
    
    scheme = {
        "scheme_name": "测试方案",
        "scheme_desc": "用于测试的方案",
        "conditions": [
            {"field": "change_pct", "op": ">", "value": 1.0, "logic": "AND"}
        ],
        "stop_loss_pct": 2.0,
        "take_profit_pct": 4.0,
        "max_hold_time": 30,
        "is_active": 1,
        "use_backtest": 1,
        "use_realtime": 1,
        "use_replay": 1
    }
    
    try:
        response = requests.post(
            f'{API_BASE}/quant-schemes',
            json=scheme,
            headers={'Content-Type': 'application/json'},
            timeout=5
        )
        print(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"成功: {data.get('success')}")
            print(f"消息: {data.get('message')}")
            return True
        else:
            print(f"错误: {response.text}")
            return False
    except Exception as e:
        print(f"请求失败: {e}")
        return False

if __name__ == '__main__':
    print("测试 quant-schemes API")
    print("请确保Web服务已启动: python src/gs2026/dashboard2/app.py")
    print()
    
    result1 = test_get_schemes()
    result2 = test_save_scheme()
    
    print("\n" + "=" * 60)
    print("测试结果:")
    print(f"  获取方案: {'通过' if result1 else '失败'}")
    print(f"  保存方案: {'通过' if result2 else '失败'}")
    print("=" * 60)
