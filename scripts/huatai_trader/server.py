"""
HTTP鏈嶅姟妯″潡
鎻愪緵REST API鎺ュ彛渚涢噺鍖栫郴缁熻皟鐢?"""

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from flask import Flask, request, jsonify
except ImportError:
    raise ImportError("璇峰厛瀹夎 flask: pip install flask")

from trader import HuaTaiTrader


def _find_config_path() -> Path:
    """鑷姩瀹氫綅 configs/huatai_trader/config.yaml"""
    current = Path(__file__).resolve().parent
    for _ in range(6):
        candidate = current / "configs" / "huatai_trader" / "config.yaml"
        if candidate.exists():
            return candidate
        current = current.parent
    raise FileNotFoundError("鎵句笉鍒?configs/huatai_trader/config.yaml")


def setup_logging(config: dict):
    """璁剧疆鏃ュ織"""
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
    """
    浜ゆ槗鍔╂墜HTTP鏈嶅姟
    
    API绔偣锛?    - POST /api/prepare_buy    鍑嗗涔板叆锛堝彧闇€浼燾ode锛?    - POST /api/prepare_sell   鍑嗗鍗栧嚭锛堝彧闇€浼燾ode锛?    - GET  /api/status         鑾峰彇鐘舵€?    - POST /api/connect        杩炴帴杞欢
    - GET  /api/health         鍋ュ悍妫€鏌?    """
    
    def __init__(self, config_path: str = None):
        """鍒濆鍖栨湇鍔?""
        if config_path is None:
            config_path = _find_config_path()
        
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        self.logger = setup_logging(self.config.get('logging', {}))
        self.trader = HuaTaiTrader(str(config_path))
        
        # 鍚姩鏃惰嚜鍔ㄨ繛鎺ュ崕娉拌蒋浠?        success, msg = self.trader.connect()
        if success:
            self.logger.info(f"鑷姩杩炴帴鍗庢嘲杞欢鎴愬姛: {msg}")
        else:
            self.logger.warning(f"鑷姩杩炴帴鍗庢嘲杞欢澶辫触: {msg}锛堝彲绋嶅悗閫氳繃 /api/connect 閲嶈瘯锛?)
        
        # 鍒涘缓Flask搴旂敤
        self.app = Flask(__name__)
        self._register_routes()
    
    def _register_routes(self):
        """娉ㄥ唽API璺敱"""
        
        @self.app.route('/api/prepare_buy', methods=['POST'])
        def api_prepare_buy():
            """
            鍑嗗涔板叆濮旀墭
            
            璇锋眰浣擄細
            {
                "code": "123257",       // 蹇呭～ - 璇佸埜浠ｇ爜
                "name": "缇庤杞€?,     // 鍙€?- 鍚嶇О锛堜粎鏃ュ織锛?                "price": 105.20,        // 鍙€?- 鏄惧紡浼犲叆鏃跺～鍏呬环鏍?                "lots": 1              // 鍙€?- 鏄惧紡浼犲叆鏃跺～鍏呮暟閲?            }
            """
            try:
                data = request.get_json()
                if not data:
                    return jsonify({'success': False, 'error': '璇锋眰浣撲负绌?}), 400
                
                bond_code = data.get('code')
                if not bond_code:
                    return jsonify({'success': False, 'error': '缂哄皯鍙傛暟: code'}), 400
                
                bond_name = data.get('name', '')
                price = data.get('price')      # None = 涓嶅～浠锋牸
                lots = data.get('lots')        # None = 涓嶅～鏁伴噺锛堥櫎闈為厤缃负fixed锛?                
                # 浜ゆ槗鏃舵妫€鏌ワ紙鍙€氳繃閰嶇疆鍏抽棴锛?                if self.config.get('hours', {}).get('check_enabled', True):
                    if not self.trader.is_trading_time():
                        return jsonify({
                            'success': False,
                            'error': f'闈炰氦鏄撴椂娈? {self.trader.get_trading_status()}'
                        }), 403
                
                self.logger.info(f"鏀跺埌涔板叆璇锋眰: {bond_code} {bond_name} price={price} lots={lots}")
                
                # 鎵ц濉厖锛坱rader鍐呴儴澶勭悊price/lots鏄惁濉厖锛?                success, msg = self.trader.prepare_buy_order(bond_code, bond_name, price, lots)
                
                if success:
                    return jsonify({
                        'success': True,
                        'message': msg,
                        'data': {'code': bond_code, 'name': bond_name, 'side': 'buy'}
                    })
                else:
                    return jsonify({'success': False, 'error': msg}), 400
                    
            except Exception as e:
                self.logger.error(f"涔板叆鍑嗗寮傚父: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/prepare_sell', methods=['POST'])
        def api_prepare_sell():
            """
            鍑嗗鍗栧嚭濮旀墭
            
            璇锋眰浣撳悓 prepare_buy
            """
            try:
                data = request.get_json()
                if not data:
                    return jsonify({'success': False, 'error': '璇锋眰浣撲负绌?}), 400
                
                bond_code = data.get('code')
                if not bond_code:
                    return jsonify({'success': False, 'error': '缂哄皯鍙傛暟: code'}), 400
                
                bond_name = data.get('name', '')
                price = data.get('price')
                lots = data.get('lots')
                
                if self.config.get('hours', {}).get('check_enabled', True):
                    if not self.trader.is_trading_time():
                        return jsonify({
                            'success': False,
                            'error': f'闈炰氦鏄撴椂娈? {self.trader.get_trading_status()}'
                        }), 403
                
                self.logger.info(f"鏀跺埌鍗栧嚭璇锋眰: {bond_code} {bond_name} price={price} lots={lots}")
                
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
                self.logger.error(f"鍗栧嚭鍑嗗寮傚父: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/status', methods=['GET'])
        def api_status():
            """鑾峰彇绯荤粺鐘舵€?""
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
            """杩炴帴鍗庢嘲杞欢"""
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
            """鍋ュ悍妫€鏌?""
            return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})
    
    def run(self):
        """鍚姩鏈嶅姟"""
        host = self.config['server']['host']
        port = self.config['server']['port']
        
        self.logger.info(f"=" * 50)
        self.logger.info(f"鍗庢嘲浜ゆ槗鍔╂墜鏈嶅姟鍚姩")
        self.logger.info(f"鐩戝惉鍦板潃: http://{host}:{port}")
        self.logger.info(f"浠锋牸妯″紡: {self.trader.price_mode}")
        self.logger.info(f"鏁伴噺妯″紡: {self.trader.quantity_mode}")
        self.logger.info(f"鎻愮ず闊? {'寮€鍚? if self.trader.sound_enabled else '鍏抽棴'}")
        self.logger.info(f"=" * 50)
        
        # 绂佺敤Flask/Werkzeug榛樿鏃ュ織
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        
        self.app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


def start_server(config_path: str = None):
    """鍚姩鏈嶅姟鐨勫叆鍙ｅ嚱鏁?""
    server = TradeServer(config_path)
    server.run()


if __name__ == '__main__':
    start_server()

