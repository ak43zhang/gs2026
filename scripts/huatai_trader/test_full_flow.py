"""
完整流程串联测试 - Web面板版
启动临时服务器,打开浏览器,模拟真实交易流程

用法: python test_full_flow.py
"""

import time
import sys
import threading
import webbrowser
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(message)s')

sys.path.insert(0, str(Path(__file__).parent))

from trade_flow import TradeFlowManager
from trade_panel_routes import create_trade_blueprint

# ==================== 配置 ====================

PORT = 8081
ACTUALLY_EXECUTE = True  # True=真操作华泰, False=仅测试面板流程

# 模拟命中数据(10条)
MOCK_HITS = [
    {'bond_code': '127045', 'bond_name': '凯中转债', 'hit_price': 105.0,
     'scheme_detail': {'name': '强势反弹', 'price_offset': 0.3, 'offset_mode': 'fixed', 'take_profit': 3.0, 'stop_loss': 2.0}, 'lots': 1},
    {'bond_code': '128015', 'bond_name': '国城转债', 'hit_price': 110.5,
     'scheme_detail': {'name': '突破', 'price_offset': 0.5, 'offset_mode': 'fixed', 'take_profit': 5.0, 'stop_loss': 3.0}, 'lots': 1},
    {'bond_code': '123045', 'bond_name': '华锐转债', 'hit_price': 98.2,
     'scheme_detail': {'name': '低吸', 'price_offset': 0.2, 'offset_mode': 'fixed', 'take_profit': 4.0, 'stop_loss': 2.5}, 'lots': 1},
    {'bond_code': '128096', 'bond_name': '众兴转债', 'hit_price': 112.8,
     'scheme_detail': {'name': '强势反弹', 'price_offset': 0.3, 'offset_mode': 'fixed', 'take_profit': 3.0, 'stop_loss': 2.0}, 'lots': 1},
    {'bond_code': '123087', 'bond_name': '明电转债', 'hit_price': 101.5,
     'scheme_detail': {'name': '突破', 'price_offset': 0.4, 'offset_mode': 'fixed', 'take_profit': 3.5, 'stop_loss': 2.0}, 'lots': 1},
    {'bond_code': '127035', 'bond_name': '朗科转债', 'hit_price': 95.3,
     'scheme_detail': {'name': '低吸', 'price_offset': 0.2, 'offset_mode': 'fixed', 'take_profit': 5.0, 'stop_loss': 3.0}, 'lots': 1},
    {'bond_code': '128023', 'bond_name': '亚康转债', 'hit_price': 108.7,
     'scheme_detail': {'name': '强势反弹', 'price_offset': 0.5, 'offset_mode': 'fixed', 'take_profit': 3.0, 'stop_loss': 2.0}, 'lots': 1},
    {'bond_code': '123056', 'bond_name': '溢利转债', 'hit_price': 99.8,
     'scheme_detail': {'name': '突破', 'price_offset': 0.3, 'offset_mode': 'fixed', 'take_profit': 4.0, 'stop_loss': 2.5}, 'lots': 1},
    {'bond_code': '127068', 'bond_name': '鸿路转债', 'hit_price': 115.2,
     'scheme_detail': {'name': '强势反弹', 'price_offset': 0.4, 'offset_mode': 'fixed', 'take_profit': 3.0, 'stop_loss': 2.0}, 'lots': 1},
    {'bond_code': '128042', 'bond_name': '转债十号', 'hit_price': 103.6,
     'scheme_detail': {'name': '低吸', 'price_offset': 0.2, 'offset_mode': 'fixed', 'take_profit': 4.5, 'stop_loss': 2.5}, 'lots': 1},
]

# ==================== 主流程 ====================

def main():
    print(f"""
╔══════════════════════════════════════════════════╗
║  交易流程串联测试 (Web面板版)                     ║
╠══════════════════════════════════════════════════╣
║  1. 启动Flask服务 (:{PORT})                      ║
║  2. 打开浏览器面板                                ║
║  3. 模拟命中信号                                  ║
║  4. 在面板上操作完成流程                           ║
║                                                  ║
║  执行模式: {'真实(操作华泰)' if ACTUALLY_EXECUTE else '模拟(不操作华泰)'}
╚══════════════════════════════════════════════════╝
    """)

    # 初始化 TradeFlowManager
    positions_file = str(Path(__file__).parent / 'tp_sl_positions.json')
    config = {
        'enabled': True,
        'positions_file': positions_file if Path(positions_file).exists() else '',
        'state_dir': str(Path(__file__).parent),
        'trader_api_url': f'http://127.0.0.1:{PORT}',
    }

    # 如果不实际执行,禁用TpSlPlacer
    if not ACTUALLY_EXECUTE:
        config['positions_file'] = ''

    manager = TradeFlowManager(config)

    # 如果是模拟模式,mock掉止盈止损
    if not ACTUALLY_EXECUTE:
        class MockPlacer:
            def place(self, *args, **kwargs):
                time.sleep(2)  # 模拟耗时
                print("  [MOCK] 模拟提交止盈止损条件单成功")
                return {'success': True, 'message': '模拟成功'}
        manager.tp_sl_placer = MockPlacer()

    # 启动Flask
    try:
        from flask import Flask
    except ImportError:
        print("  [!] 需要Flask: pip install flask")
        sys.exit(1)

    app = Flask(__name__)
    bp = create_trade_blueprint(manager)
    app.register_blueprint(bp)

    # 模拟买入API(如果真实服务没启动)
    @app.route('/api/prepare_buy', methods=['POST'])
    def mock_prepare_buy():
        from flask import jsonify, request
        data = request.get_json()
        print(f"  [BUY] 填充买入: {data.get('code')} @{data.get('price')} x{data.get('lots')}手")
        return jsonify({'success': True, 'message': '买入已填充'})

    @app.route('/api/cancel_order', methods=['POST'])
    def mock_cancel():
        from flask import jsonify, request
        data = request.get_json()
        print(f"  [CANCEL] 撤单: {data.get('code')}")
        return jsonify({'success': True, 'message': '已撤单'})

    # 超时检查线程
    def timeout_loop():
        while True:
            manager.check_timeout()
            time.sleep(1)

    threading.Thread(target=timeout_loop, daemon=True).start()

    # 延迟发送模拟命中
    def send_mock_hits():
        time.sleep(2)
        print("\n  [SIM] 发送模拟命中信号...")
        for i, hit in enumerate(MOCK_HITS):
            manager.on_hit(
                bond_code=hit['bond_code'],
                bond_name=hit['bond_name'],
                hit_price=hit['hit_price'],
                scheme_detail=hit['scheme_detail'],
                lots=hit['lots'],
            )
            print(f"  [SIM] 命中{i+1}: {hit['bond_name']}({hit['bond_code']}) @{hit['hit_price']}")
            time.sleep(0.5)
        print(f"\n  [SIM] 已发送{len(MOCK_HITS)}个命中,请在面板操作")

    threading.Thread(target=send_mock_hits, daemon=True).start()

    # 打开浏览器
    def open_browser():
        time.sleep(1)
        url = f"http://127.0.0.1:{PORT}/panel"
        print(f"\n  打开面板: {url}")
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()

    # 启动服务
    print(f"  启动服务 http://127.0.0.1:{PORT}/panel")
    print("  按Ctrl+C停止\n")
    app.run(host='127.0.0.1', port=PORT, debug=False, use_reloader=False)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n停止")


