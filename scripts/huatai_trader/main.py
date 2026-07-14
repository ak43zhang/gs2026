"""
华泰交易助手 - 主入口

启动方式：
    python -m huatai_trader.main
    
或：
    python scripts/huatai_trader/main.py
"""

import sys
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from huatai_trader.server import start_server


if __name__ == '__main__':
    print("=" * 60)
    print("华泰证券可转债半自动交易助手")
    print("=" * 60)
    print()
    print("功能说明：")
    print("  1. 接收量化系统的交易信号")
    print("  2. 弹出确认窗口（30秒超时）")
    print("  3. 用户确认后自动填充华泰软件")
    print("  4. 人工在华泰界面点击最终确认")
    print()
    print("安全声明：")
    print("  • 不存储交易密码")
    print("  • 不自动提交订单")
    print("  • 所有操作本地执行")
    print()
    print("API端点：")
    print("  POST http://127.0.0.1:8081/api/prepare_buy")
    print("  POST http://127.0.0.1:8081/api/prepare_sell")
    print("  GET  http://127.0.0.1:8081/api/status")
    print()
    print("按 Ctrl+C 停止服务")
    print("=" * 60)
    print()
    
    try:
        start_server()
    except KeyboardInterrupt:
        print("\n服务已停止")
        sys.exit(0)
