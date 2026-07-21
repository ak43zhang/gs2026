"""
华泰交易助手 - 主入口

启动方式：
    cd scripts/huatai_trader
    python main.py
    
或从项目根目录：
    python scripts/huatai_trader/main.py
"""

import sys
from pathlib import Path

# 添加scripts目录到路径
scripts_dir = Path(__file__).parent
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

from server import start_server
from trade_hook import init_trade_hook


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
    print("  面板 http://127.0.0.1:8081/api/auto_trade/panel")
    print()
    print("按 Ctrl+C 停止服务")
    print("=" * 60)
    print()
    
    # 初始化自动交易Hook
    try:
        config = {
            'enabled': True,
            'mode': 'full',  # full=全自动(买入→TP/SL→卖出), buy_only=只买入
            'signal_expire_seconds': 120,
            'fill_timeout_seconds': 30,
            'popup_poll_ms': 100,
            'sounds': {'enabled': True},
        }
        init_trade_hook(config)
        print(f"[AutoTrader] 已启用, mode={config['mode']}")
        
        # 初始化MySQL命中记录表
        import hit_store
        if hit_store.init_table():
            print("[AutoTrader] MySQL命中记录表就绪")
        else:
            print("[AutoTrader] MySQL初始化失败(不影响运行)")
    except Exception as e:
        print(f"[AutoTrader] 初始化失败: {e}")
    
    print()
    
    try:
        start_server()
    except KeyboardInterrupt:
        print("\n服务已停止")
        sys.exit(0)
