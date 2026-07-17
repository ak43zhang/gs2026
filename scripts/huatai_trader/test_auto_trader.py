"""
自动止盈止损系统 - 独立测试脚本
不依赖 monitor_bond.py，可单独运行测试完整流程

用法:
    cd scripts/huatai_trader
    python test_auto_trader.py

测试内容:
    1. 模拟命中信号推送
    2. Web面板操作
    3. 成交弹窗检测
    4. 止盈止损设置
    5. 持仓监控
"""

import time
import json
import random
import threading
from datetime import datetime
from pathlib import Path

# 确保可以导入本地模块
import sys
sys.path.insert(0, str(Path(__file__).parent))

from auto_trader import get_auto_trader
from trade_hook import init_trade_hook


def test_full_flow():
    """测试完整流程"""
    print("=" * 60)
    print("自动止盈止损系统 - 完整流程测试")
    print("=" * 60)
    print()
    
    # 初始化
    config = {
        'enabled': True,
        'signal_expire_seconds': 30,
        'fill_timeout_seconds': 30,
        'popup_poll_ms': 100,
        'sounds': {'enabled': False},  # 测试时关闭声音
    }
    
    init_trade_hook(config)
    trader = get_auto_trader(config)
    
    print("✓ 系统初始化完成")
    print(f"  状态: {trader.get_status()['state']}")
    print()
    
    # ========== 测试1: 命中信号 ==========
    print("【测试1】模拟命中信号推送")
    print("-" * 40)
    
    test_signals = [
        {
            'code': '127045',
            'name': '凯中转债',
            'price': 105.5,
            'scheme': {
                'name': '测试方案A',
                'take_profit': 3.0,
                'stop_loss': 2.0,
                'max_hold_time': 30,
            },
            'lots': 1,
        },
        {
            'code': '127011',
            'name': '国城转债',
            'price': 111.0,
            'scheme': {
                'name': '测试方案B',
                'take_profit': 5.0,
                'stop_loss': 3.0,
                'max_hold_time': 30,
            },
            'lots': 2,
        },
    ]
    
    for signal in test_signals:
        trader.on_hit(
            signal['code'],
            signal['name'],
            signal['price'],
            signal['scheme'],
            signal['lots']
        )
        print(f"  推送: {signal['code']} {signal['name']} @ {signal['price']}")
        time.sleep(0.5)
    
    status = trader.get_status()
    print(f"\n  当前状态: {status['state']}")
    print(f"  命中列表: {len(status['hit_list'])} 条")
    for hit in status['hit_list']:
        print(f"    - {hit['code']} {hit['name']} TP={hit['tp_pct']}% SL={hit['sl_pct']}%")
    print()
    
    # ========== 测试2: 用户选择买入 ==========
    print("【测试2】模拟用户点击买入")
    print("-" * 40)
    
    if status['hit_list']:
        code = status['hit_list'][0]['code']
        result = trader.on_buy_click(code)
        print(f"  买入 {code}: {result}")
        
        time.sleep(1)
        status = trader.get_status()
        print(f"\n  当前状态: {status['state']}")
        if status['current']:
            print(f"  当前交易: {status['current']['code']} {status['current']['name']}")
    print()
    
    # ========== 测试3: 模拟成交检测 ==========
    print("【测试3】模拟成交弹窗检测")
    print("-" * 40)
    print("  注意: 实际需要在华泰软件中点击买入")
    print("  测试模式: 5秒后模拟成交...")
    
    # 实际测试中，这里会等待真实的成交弹窗
    # 测试模式下，我们模拟成交
    time.sleep(5)
    
    # 模拟进入监控状态
    with trader._lock:
        if trader._state.state == "TRADING":
            # 模拟成交成功
            hit = trader._state.current
            if hit:
                trader._state.fill_time = time.time()
                trader._state.tp_level = hit.buy_price * (1 + hit.tp_pct / 100)
                trader._state.sl_level = hit.buy_price * (1 - hit.sl_pct / 100)
                trader._state.max_hold_seconds = hit.max_hold_minutes * 60
                trader._state.state = "MONITORING"
                print(f"  ✓ 模拟成交成功")
                print(f"    买入价: {hit.buy_price}")
                print(f"    止盈价: {trader._state.tp_level:.3f}")
                print(f"    止损价: {trader._state.sl_level:.3f}")
    
    status = trader.get_status()
    print(f"\n  当前状态: {status['state']}")
    print()
    
    # ========== 测试4: 持仓监控 ==========
    print("【测试4】模拟持仓监控")
    print("-" * 40)
    
    # 模拟价格变动
    print("  模拟价格变动...")
    
    for i in range(10):
        # 构造模拟行情数据
        current = trader._state.current
        if not current:
            break
        
        # 模拟价格波动
        price_change = random.uniform(-0.5, 0.8)
        current_price = current.buy_price * (1 + price_change / 100)
        
        # 构造DataFrame
        import pandas as pd
        df = pd.DataFrame([{
            'bond_code': current.code,
            'price': current_price,
        }])
        
        # 调用on_tick
        trader.on_tick(df)
        
        profit_pct = (current_price - current.buy_price) / current.buy_price * 100
        print(f"    价格: {current_price:.3f} ({profit_pct:+.2f}%)")
        
        # 检查状态
        status = trader.get_status()
        if status['state'] == 'IDLE':
            print(f"\n  ✓ 交易结束!")
            if status['history']:
                last = status['history'][-1]
                print(f"    结果: {last['reason']}")
                print(f"    盈亏: {last.get('exit_price', 0) - last['buy_price']:.3f}")
            break
        
        time.sleep(0.5)
    
    print()
    
    # ========== 测试5: 查看历史 ==========
    print("【测试5】查看交易历史")
    print("-" * 40)
    
    status = trader.get_status()
    history = status.get('history', [])
    
    if history:
        print(f"  共 {len(history)} 笔交易")
        for h in history:
            print(f"    {h['code']} {h['name']} - {h['reason']}")
    else:
        print("  暂无交易记录")
    
    print()
    print("=" * 60)
    print("测试完成!")
    print("=" * 60)
    print()
    print("下一步:")
    print("  1. 启动服务: python main.py")
    print("  2. 打开面板: http://127.0.0.1:8081/api/auto_trade/panel")
    print("  3. 在华泰软件中测试真实买入")
    print("  4. 运行弹窗探测: python test_popup_detect.py")


def test_api_endpoints():
    """测试API端点"""
    print("\n" + "=" * 60)
    print("API端点测试")
    print("=" * 60)
    
    import requests
    
    base_url = "http://127.0.0.1:8081/api/auto_trade"
    
    # 测试状态接口
    try:
        resp = requests.get(f"{base_url}/status", timeout=5)
        print(f"\n✓ GET /status: {resp.status_code}")
        print(f"  响应: {json.dumps(resp.json(), indent=2, ensure_ascii=False)[:200]}...")
    except Exception as e:
        print(f"\n✗ GET /status 失败: {e}")
        print("  请确保服务已启动: python main.py")
    
    # 测试买入接口
    try:
        resp = requests.post(f"{base_url}/buy/127045", timeout=5)
        print(f"\n✓ POST /buy/127045: {resp.status_code}")
        print(f"  响应: {resp.json()}")
    except Exception as e:
        print(f"\n✗ POST /buy/127045 失败: {e}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='自动止盈止损测试')
    parser.add_argument('--api', action='store_true', help='只测试API端点')
    parser.add_argument('--flow', action='store_true', help='测试完整流程')
    
    args = parser.parse_args()
    
    if args.api:
        test_api_endpoints()
    elif args.flow:
        test_full_flow()
    else:
        # 默认都测试
        test_full_flow()
        print("\n" + "=" * 60)
        print("提示: 使用 --api 参数测试API端点")
        print("      使用 --flow 参数测试完整流程")
        print("=" * 60)
