"""
HTTP服务模块
提供REST API接口供量化系统调用
"""

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from flask import Flask, request, jsonify
except ImportError:
    raise ImportError("请先安装 flask: pip install flask")

from trader import HuaTaiTrader


def _find_config_path() -> Path:
    """自动定位 configs/huatai_trader/config.yaml"""
    current = Path(__file__).resolve().parent
    for _ in range(6):
        candidate = current / "configs" / "huatai_trader" / "config.yaml"
        if candidate.exists():
            return candidate
        current = current.parent
    raise FileNotFoundError("找不到 configs/huatai_trader/config.yaml")


def setup_logging(config: dict):
    """设置日志"""
    level = getattr(logging, config.get('level', 'INFO').upper())
    log_file = config.get('file', 'huatai_trader.log')

    logger = logging.getLogger()
    logger.setLevel(level)

    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
    logger.addHandler(fh)

    if config.get('console', True):
        ch = logging.StreamHandler()
        ch.setLevel(level)
        ch.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))
        logger.addHandler(ch)

    return logger


class TradeServer:
    """交易助手HTTP服务"""

    def __init__(self, config_path: str = None):
        """初始化服务"""
        if config_path is None:
            config_path = _find_config_path()

        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        self.logger = setup_logging(self.config.get('logging', {}))
        self.trader = HuaTaiTrader(str(config_path))

        # 启动时自动连接华泰软件
        success, msg = self.trader.connect()
        if success:
            self.logger.info(f"自动连接华泰软件成功: {msg}")
        else:
            self.logger.warning(f"自动连接华泰软件失败: {msg}")

        # 创建Flask应用
        self.app = Flask(__name__)
        self._register_routes()

    def _register_routes(self):
        """注册API路由"""

        @self.app.route('/api/prepare_buy', methods=['POST'])
        def api_prepare_buy():
            """准备买入委托"""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({'success': False, 'error': '请求体为空'}), 400

                bond_code = data.get('code')
                if not bond_code:
                    return jsonify({'success': False, 'error': '缺少参数: code'}), 400

                bond_name = data.get('name', '')
                price = data.get('price')
                lots = data.get('lots')

                # 交易时段检查
                if self.config.get('hours', {}).get('check_enabled', True):
                    if not self.trader.is_trading_time():
                        return jsonify({
                            'success': False,
                            'error': f'非交易时段: {self.trader.get_trading_status()}'
                        }), 403

                self.logger.info(f"收到买入请求: {bond_code} {bond_name}")

                success, msg = self.trader.prepare_buy_order(bond_code, bond_name, price, lots)

                if success:
                    return jsonify({
                        'success': True,
                        'message': msg,
                        'data': {'code': bond_code, 'name': bond_name, 'side': 'buy'}
                    })
                else:
                    return jsonify({'success': False, 'error': msg}), 400

            except Exception as e:
                self.logger.error(f"买入准备异常: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.app.route('/api/prepare_sell', methods=['POST'])
        def api_prepare_sell():
            """准备卖出委托"""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({'success': False, 'error': '请求体为空'}), 400

                bond_code = data.get('code')
                if not bond_code:
                    return jsonify({'success': False, 'error': '缺少参数: code'}), 400

                bond_name = data.get('name', '')
                price = data.get('price')
                lots = data.get('lots')

                if self.config.get('hours', {}).get('check_enabled', True):
                    if not self.trader.is_trading_time():
                        return jsonify({
                            'success': False,
                            'error': f'非交易时段: {self.trader.get_trading_status()}'
                        }), 403

                self.logger.info(f"收到卖出请求: {bond_code} {bond_name}")

                success, msg = self.trader.prepare_sell_order(bond_code, bond_name, price, lots)

                if success:
                    return jsonify({
                        'success': True,
                        'message': msg,
                        'data': {'code': bond_code, 'name': bond_name, 'side': 'sell'}
                    })
                else:
                    return jsonify({'success': False, 'error': msg}), 400

            except Exception as e:
                self.logger.error(f"卖出准备异常: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.app.route('/api/status', methods=['GET'])
        def api_status():
            """获取系统状态"""
            try:
                status = {
                    'connected': self.trader.is_connected(),
                    'is_trading_time': self.trader.is_trading_time(),
                    'trading_status': self.trader.get_trading_status(),
                    'config': {
                        'price_mode': self.trader.price_mode,
                        'quantity_mode': self.trader.quantity_mode,
                        'sound_enabled': self.trader.sound_enabled,
                    }
                }
                return jsonify({'success': True, 'data': status})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.app.route('/api/connect', methods=['POST'])
        def api_connect():
            """连接华泰软件"""
            try:
                success, msg = self.trader.connect()
                if success:
                    return jsonify({'success': True, 'message': msg})
                else:
                    return jsonify({'success': False, 'error': msg}), 500
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.app.route('/api/health', methods=['GET'])
        def api_health():
            """健康检查"""
            return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

    def run(self):
        """启动服务"""
        server_cfg = self.config.get('server', {})
        host = server_cfg.get('host', '127.0.0.1')
        port = server_cfg.get('port', 8081)

        self.logger.info("=" * 50)
        self.logger.info("华泰交易助手服务启动")
        self.logger.info(f"监听地址: http://{host}:{port}")
        self.logger.info(f"价格模式: {self.trader.price_mode}")
        self.logger.info(f"数量模式: {self.trader.quantity_mode}")
        self.logger.info(f"提示音: {'开启' if self.trader.sound_enabled else '关闭'}")
        self.logger.info("=" * 50)

        # 禁用Flask/Werkzeug默认日志
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)

        self.app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


def start_server(config_path: str = None):
    """启动服务的入口函数"""
    server = TradeServer(config_path)
    server.run()


if __name__ == '__main__':
    start_server()
