#!/usr/bin/env python3
"""
API测试工具
测试各模块API接口

使用示例:
    python tools/api_tester.py --endpoint /api/stock-picker/search --params "q=电力&limit=10"
    python tools/api_tester.py --endpoint /api/stock-picker/query --method POST --data '{"tags":["industry:881145"]}'
    python tools/api_tester.py --test-all
"""
import sys
sys.path.insert(0, 'src')

import argparse
import json
import requests

BASE_URL = "http://localhost:8080"


def test_endpoint(endpoint: str, method: str = 'GET', params: dict = None, data: dict = None):
    """测试API端点"""
    url = f"{BASE_URL}{endpoint}"
    
    print(f"\n=== 测试: {method} {endpoint} ===")
    
    try:
        if method.upper() == 'GET':
            resp = requests.get(url, params=params, timeout=10)
        else:
            resp = requests.post(url, json=data, timeout=10)
        
        print(f"状态码: {resp.status_code}")
        
        if resp.status_code == 200:
            result = resp.json()
            print(f"响应码: {result.get('code', 'N/A')}")
            print(f"消息: {result.get('message', 'N/A')}")
            
            if 'data' in result:
                data = result['data']
                if isinstance(data, list):
                    print(f"数据条数: {len(data)}")
                    if data:
                        print(f"首条样本: {json.dumps(data[0], ensure_ascii=False)[:200]}...")
                elif isinstance(data, dict):
                    print(f"数据键: {list(data.keys())}")
            
            return True
        else:
            print(f"错误: {resp.text[:200]}")
            return False
            
    except Exception as e:
        print(f"请求失败: {e}")
        return False


def test_stock_picker():
    """测试智能选股API"""
    print("\n" + "="*50)
    print("智能选股API测试")
    print("="*50)
    
    # 搜索
    test_endpoint('/api/stock-picker/search', params={'q': '电力', 'limit': 5})
    test_endpoint('/api/stock-picker/search', params={'q': 'dl', 'limit': 5})
    
    # 查询
    test_endpoint('/api/stock-picker/query', params={'tags': 'industry:881145'})
    test_endpoint('/api/stock-picker/query', params={'tags': 'industry:881145,concept:309055'})


def test_monitor():
    """测试数据监控API"""
    print("\n" + "="*50)
    print("数据监控API测试")
    print("="*50)
    
    test_endpoint('/api/monitor/timestamps', params={'date': '20260421'})
    test_endpoint('/api/monitor/attack-ranking/industry', params={'date': '20260421', 'limit': 5})


def test_all():
    """测试所有API"""
    test_stock_picker()
    test_monitor()


def main():
    parser = argparse.ArgumentParser(description='API测试工具')
    parser.add_argument('--endpoint', help='API端点')
    parser.add_argument('--method', default='GET', help='请求方法')
    parser.add_argument('--params', help='URL参数 (key=value&...)')
    parser.add_argument('--data', help='POST数据 (JSON)')
    parser.add_argument('--test-stock-picker', action='store_true', help='测试智能选股')
    parser.add_argument('--test-monitor', action='store_true', help='测试数据监控')
    parser.add_argument('--test-all', action='store_true', help='测试所有')
    
    args = parser.parse_args()
    
    if args.endpoint:
        params = {}
        if args.params:
            for pair in args.params.split('&'):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    params[k] = v
        
        data = json.loads(args.data) if args.data else None
        test_endpoint(args.endpoint, args.method, params, data)
    elif args.test_stock_picker:
        test_stock_picker()
    elif args.test_monitor:
        test_monitor()
    elif args.test_all:
        test_all()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
