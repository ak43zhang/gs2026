"""
交易助手端到端测试脚本
模拟从命中检测到华泰软件填充的完整流程

使用方法：
    cd F:\pyworkspace2026\gs2026
    .venv\Scripts\python scripts\huatai_trader\test_e2e.py

前置条件：
    1. 交易助手服务已启动（python scripts/huatai_trader/main.py）
    2. 华泰证券软件已运行并登录
"""

import sys
import time
import requests

TRADER_API_URL = "http://127.0.0.1:8081"

# 测试用债券数据
TEST_BONDS = [
    {"code": "123257", "name": "美诺转债", "price": 105.20, "lots": 1},
    {"code": "127060", "name": "天赐转债", "price": 112.50, "lots": 1},
    {"code": "113050", "name": "南银转债", "price": 98.80, "lots": 1},
]


def check_service():
    """检查交易助手服务是否可用"""
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
        print(f"  → 请先启动服务: .venv\\Scripts\\python scripts\\huatai_trader\\main.py")
        return False
    except Exception as e:
        print(f"  ✗ 错误: {e}")
        return False


def check_status():
    """检查华泰软件连接状态"""
    print("\n" + "=" * 50)
    print("【步骤2】检查华泰软件连接")
    print("=" * 50)
    try:
        r = requests.get(f"{TRADER_API_URL}/api/status", timeout=5)
        data = r.json()
        if data.get('success'):
            status = data.get('data', {})
            print(f"  连接状态: {status.get('connected', '未知')}")
            print(f"  交易时段: {status.get('is_trading_time', '未知')}")
            return True
        else:
            print(f"  ✗ 状态查询失败: {data.get('error')}")
            return False
    except Exception as e:
        print(f"  ✗ 错误: {e}")
        return False


def test_prepare_buy(bond):
    """测试买入准备"""
    print(f"\n{'─' * 50}")
    print(f"  发送买入请求:")
    print(f"    代码: {bond['code']}")
    print(f"    名称: {bond['name']}")
    print(f"    价格: {bond['price']} 元")
    print(f"    数量: {bond['lots']} 手 ({bond['lots'] * 10} 张)")
    print(f"    金额: {bond['price'] * bond['lots'] * 10:.2f} 元")
    print(f"{'─' * 50}")
    
    try:
        r = requests.post(
            f"{TRADER_API_URL}/api/prepare_buy",
            json=bond,
            timeout=35
        )
        data = r.json()
        
        if data.get('success'):
            print(f"  ✓ 准备成功: {data.get('message', '')}")
            print(f"  → 请查看华泰软件买入界面，确认信息已填充")
            return True
        else:
            print(f"  ✗ 准备失败: {data.get('error', '未知错误')}")
            return False
    except requests.exceptions.Timeout:
        print(f"  ✗ 请求超时（35秒）")
        return False
    except Exception as e:
        print(f"  ✗ 错误: {e}")
        return False


def test_overwrite():
    """测试覆盖行为（连续发送多个信号）"""
    print("\n" + "=" * 50)
    print("【步骤4】测试覆盖行为")
    print("  连续发送2个不同债券，验证后一个覆盖前一个")
    print("=" * 50)
    
    for i, bond in enumerate(TEST_BONDS[:2]):
        print(f"\n  >>> 发送第 {i+1} 个信号...")
        success = test_prepare_buy(bond)
        if success and i == 0:
            print(f"\n  等待2秒后发送下一个（模拟新命中覆盖）...")
            time.sleep(2)
    
    print(f"\n  → 请确认华泰软件中显示的是最后一个债券: {TEST_BONDS[1]['name']}")


def main():
    print("""
╔══════════════════════════════════════════════════╗
║         交易助手 - 端到端链路测试               ║
╚══════════════════════════════════════════════════╝
""")
    
    # 步骤1：检查服务
    if not check_service():
        sys.exit(1)
    
    # 步骤2：检查状态
    check_status()
    
    # 步骤3：选择测试模式
    print("\n" + "=" * 50)
    print("【步骤3】选择测试模式")
    print("=" * 50)
    print("  1. 单次买入测试（发送1个信号）")
    print("  2. 覆盖测试（连续发送2个信号，验证覆盖）")
    print("  3. 自定义测试（输入债券代码和价格）")
    print("  q. 退出")
    
    while True:
        choice = input("\n请选择 [1/2/3/q]: ").strip()
        
        if choice == '1':
            print("\n" + "=" * 50)
            print("【单次买入测试】")
            print("=" * 50)
            test_prepare_buy(TEST_BONDS[0])
            print("\n  ✓ 测试完成！请在华泰软件中确认信息并点击'买入'")
            
        elif choice == '2':
            test_overwrite()
            print("\n  ✓ 覆盖测试完成！")
            
        elif choice == '3':
            code = input("  债券代码: ").strip()
            name = input("  债券名称: ").strip() or code
            price = float(input("  价格: ").strip())
            lots = int(input("  手数 [1]: ").strip() or "1")
            
            bond = {"code": code, "name": name, "price": price, "lots": lots}
            test_prepare_buy(bond)
            
        elif choice == 'q':
            print("\n退出测试。")
            break
        else:
            print("  无效选择")


if __name__ == '__main__':
    main()
