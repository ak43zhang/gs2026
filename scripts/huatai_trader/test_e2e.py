"""
交易助手端到端测试脚本
默认只传证券代码，价格和数量由软件/配置控制

使用方法：
    cd F:\pyworkspace2026\gs2026
    .venv\Scripts\python scripts\huatai_trader\test_e2e.py
"""

import sys
import time
import requests

TRADER_API_URL = "http://127.0.0.1:8081"

# 测试用债券
TEST_BONDS = [
    {"code": "123257", "name": "美诺转债"},
    {"code": "127060", "name": "天赐转债"},
    {"code": "113050", "name": "南银转债"},
]


def check_service():
    """检查服务是否可用"""
    print("=" * 50)
    print("【步骤1】检查交易助手服务")
    print("=" * 50)
    try:
        r = requests.get(f"{TRADER_API_URL}/api/health", timeout=3)
        data = r.json()
        print(f"  ✓ 服务正常: {data}")
        return True
    except requests.exceptions.ConnectionError:
        print(f"  ✗ 无法连接 {TRADER_API_URL}")
        print(f"  → 请先启动: .venv\\Scripts\\python scripts\\huatai_trader\\main.py")
        return False
    except Exception as e:
        print(f"  ✗ 错误: {e}")
        return False


def check_status():
    """检查状态"""
    print("\n" + "=" * 50)
    print("【步骤2】检查系统状态")
    print("=" * 50)
    try:
        r = requests.get(f"{TRADER_API_URL}/api/status", timeout=5)
        data = r.json()
        if data.get('success'):
            status = data.get('data', {})
            config = status.get('config', {})
            print(f"  连接状态: {status.get('connected')}")
            print(f"  交易时段: {status.get('is_trading_time')}")
            print(f"  价格模式: {config.get('price_mode')} (auto=软件默认)")
            print(f"  数量模式: {config.get('quantity_mode')} (auto=软件默认)")
            print(f"  提示音: {config.get('sound_enabled')}")
            return status.get('connected', False)
    except Exception as e:
        print(f"  ✗ 错误: {e}")
    return False


def test_buy_code_only(bond):
    """测试：只传代码"""
    print(f"\n{'─' * 50}")
    print(f"  模式：只传代码（价格/数量由软件自动处理）")
    print(f"  代码: {bond['code']} ({bond['name']})")
    print(f"{'─' * 50}")
    
    try:
        r = requests.post(
            f"{TRADER_API_URL}/api/prepare_buy",
            json={"code": bond['code'], "name": bond['name']},
            timeout=10
        )
        data = r.json()
        if data.get('success'):
            print(f"  ✓ {data.get('message')}")
            return True
        else:
            print(f"  ✗ {data.get('error')}")
            return False
    except Exception as e:
        print(f"  ✗ 错误: {e}")
        return False


def test_buy_with_price(bond, price):
    """测试：传代码+价格"""
    print(f"\n{'─' * 50}")
    print(f"  模式：代码+价格")
    print(f"  代码: {bond['code']} ({bond['name']})")
    print(f"  价格: {price}")
    print(f"{'─' * 50}")
    
    try:
        r = requests.post(
            f"{TRADER_API_URL}/api/prepare_buy",
            json={"code": bond['code'], "name": bond['name'], "price": price},
            timeout=10
        )
        data = r.json()
        if data.get('success'):
            print(f"  ✓ {data.get('message')}")
            return True
        else:
            print(f"  ✗ {data.get('error')}")
            return False
    except Exception as e:
        print(f"  ✗ 错误: {e}")
        return False


def test_buy_with_lots(bond, lots):
    """测试：传代码+数量"""
    print(f"\n{'─' * 50}")
    print(f"  模式：代码+数量")
    print(f"  代码: {bond['code']} ({bond['name']})")
    print(f"  数量: {lots}手 ({lots*10}张)")
    print(f"{'─' * 50}")
    
    try:
        r = requests.post(
            f"{TRADER_API_URL}/api/prepare_buy",
            json={"code": bond['code'], "name": bond['name'], "lots": lots},
            timeout=10
        )
        data = r.json()
        if data.get('success'):
            print(f"  ✓ {data.get('message')}")
            return True
        else:
            print(f"  ✗ {data.get('error')}")
            return False
    except Exception as e:
        print(f"  ✗ 错误: {e}")
        return False


def test_overwrite():
    """测试覆盖行为"""
    print("\n" + "=" * 50)
    print("【覆盖测试】连续发送2个不同债券")
    print("=" * 50)
    
    for i, bond in enumerate(TEST_BONDS[:2]):
        print(f"\n  >>> 发送第 {i+1} 个: {bond['name']}...")
        test_buy_code_only(bond)
        if i == 0:
            print(f"\n  等待2秒...")
            time.sleep(2)
    
    print(f"\n  → 华泰软件应显示最后一个: {TEST_BONDS[1]['name']}")


def main():
    print("""
╔══════════════════════════════════════════════════╗
║         交易助手 - 端到端链路测试               ║
║         默认模式：只传证券代码                   ║
╚══════════════════════════════════════════════════╝
""")
    
    if not check_service():
        sys.exit(1)
    
    connected = check_status()
    if not connected:
        print("\n  ⚠ 未连接华泰软件，尝试连接...")
        try:
            r = requests.post(f"{TRADER_API_URL}/api/connect", timeout=10)
            data = r.json()
            if data.get('success'):
                print(f"  ✓ {data.get('message')}")
            else:
                print(f"  ✗ {data.get('error')}")
                print(f"  → 请确保华泰软件已启动并登录")
        except Exception as e:
            print(f"  ✗ 连接失败: {e}")
    
    print("\n" + "=" * 50)
    print("【步骤3】选择测试模式")
    print("=" * 50)
    print("  1. 只传代码（默认，价格/数量由软件处理）")
    print("  2. 代码+价格")
    print("  3. 代码+数量")
    print("  4. 覆盖测试（连续2个信号）")
    print("  5. 自定义")
    print("  q. 退出")
    
    while True:
        choice = input("\n请选择 [1/2/3/4/5/q]: ").strip()
        
        if choice == '1':
            test_buy_code_only(TEST_BONDS[0])
            print("\n  → 请检查华泰软件买入界面")
            
        elif choice == '2':
            price = float(input("  输入价格: ").strip())
            test_buy_with_price(TEST_BONDS[0], price)
            
        elif choice == '3':
            lots = int(input("  输入手数 [1]: ").strip() or "1")
            test_buy_with_lots(TEST_BONDS[0], lots)
            
        elif choice == '4':
            test_overwrite()
            
        elif choice == '5':
            code = input("  证券代码: ").strip()
            name = input("  名称(可空): ").strip()
            price_str = input("  价格(可空): ").strip()
            lots_str = input("  手数(可空): ").strip()
            
            payload = {"code": code}
            if name:
                payload["name"] = name
            if price_str:
                payload["price"] = float(price_str)
            if lots_str:
                payload["lots"] = int(lots_str)
            
            print(f"\n  发送: {payload}")
            try:
                r = requests.post(f"{TRADER_API_URL}/api/prepare_buy", json=payload, timeout=10)
                print(f"  响应: {r.json()}")
            except Exception as e:
                print(f"  错误: {e}")
            
        elif choice == 'q':
            print("\n退出。")
            break


if __name__ == '__main__':
    main()
