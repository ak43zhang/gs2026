"""
HTTP服务模块
提供REST API接口供量化系统调用
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

# Flask用于HTTP服务
try:
    from flask import Flask, request, jsonify
except ImportError:
    raise ImportError("请先安装 flask: pip install flask")

from trader import HuaTaiTrader
from popup import TradeConfirmPopup, QuickPopup


# 配置日志
def setup_logging(config: dict):
    """设置日志"""
    level = getattr(logging, config.get('level', 'INFO').upper())
    log_file = config.get('log_file', 'huatai_trader.log')
    
    handlers = [logging.FileHandler(log_file, encoding='utf-8')]
    if config.get('console_output', True):
        handlers.append(logging.StreamHandler())
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s | %(levelname)s | %(message)s',
        handlers=handlers
    )
    return logging.getLogger(__name__)


class TradeServer:
    """
    交易助手HTTP服务
    
    API端点：
    - POST /api/prepare_buy    准备买入
    - POST /api/prepare_sell   准备卖出
    - GET  /api/status         获取状态
    - POST /api/connect        连接软件
    """
    
    def __init__(self, config_path: str = None):
        """初始化服务"""
        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"
        
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        self.logger = setup_logging(self.config.get('logging', {}))
        self.trader = HuaTaiTrader(config_path)
        self.popup_config = self.config.get('user_interface', {})
        
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
                
                # 参数验证
                bond_code = data.get('code')
                bond_name = data.get('name', '')
                price = data.get('price')
                lots = data.get('lots', self.config['convertible_bond']['default_buy_lots'])
                
                if not bond_code:
                    return jsonify({'success': False, 'error': '缺少参数: code'}), 400
                if price is None:
                    return jsonify({'success': False, 'error': '缺少参数: price'}), 400
                
                # 检查是否在交易时段
                if not self.trader.is_trading_time():
                    status = self.trader.get_trading_status()
                    return jsonify({
                        'success': False, 
                        'error': f'当前非交易时段: {status}',
                        'trading_status': status
                    }), 403
                
                # 显示确认弹窗
                quantity = lots * 10
                amount = quantity * price
                
                message = f"""债券代码: {bond_code}
债券名称: {bond_name}
委托价格: {price} 元
委托数量: {lots}手 ({quantity}张)
预估金额: {amount:.2f} 元

点击"准备委托"将自动填充华泰软件买入界面"""
                
                popup = TradeConfirmPopup(self.popup_config)
                confirmed = popup.show(
                    title="买入信号确认",
                    message=message,
                    on_confirm=lambda: self.logger.info(f"用户确认准备买入: {bond_code}")
                )
                
                if not confirmed:
                    return jsonify({
                        'success': False, 
                        'error': '用户取消',
                        'message': '用户点击忽略或超时未响应'
                    }), 200
                
                # 执行准备
                success, msg = self.trader.prepare_buy_order(bond_code, bond_name, price, lots)
                
                if success:
                    self.logger.info(f"买入准备成功: {bond_code} {lots}手 @ {price}")
                    return jsonify({
                        'success': True,
                        'message': msg,
                        'data': {
                            'code': bond_code,
                            'name': bond_name,
                            'price': price,
                            'lots': lots,
                            'quantity': quantity,
                            'amount': round(amount, 2),
                            'side': 'buy'
                        }
                    })
                else:
                    self.logger.warning(f"买入准备失败: {msg}")
                    return jsonify({
                        'success': False,
                        'error': msg
                    }), 400
                    
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
                bond_name = data.get('name', '')
                price = data.get('price')
                lots = data.get('lots', self.config['convertible_bond']['default_buy_lots'])
                
                if not bond_code:
                    return jsonify({'success': False, 'error': '缺少参数: code'}), 400
                if price is None:
                    return jsonify({'success': False, 'error': '缺少参数: price'}), 400
                
                if not self.trader.is_trading_time():
                    status = self.trader.get_trading_status()
                    return jsonify({
                        'success': False, 
                        'error': f'当前非交易时段: {status}',
                        'trading_status': status
                    }), 403
                
                quantity = lots * 10
                amount = quantity * price
                
                message = f"""债券代码: {bond_code}
债券名称: {bond_name}
委托价格: {price} 元
委托数量: {lots}手 ({quantity}张)
预估金额: {amount:.2f} 元

点击"准备委托"将自动填充华泰软件卖出界面"""
                
                popup = TradeConfirmPopup(self.popup_config)
                confirmed = popup.show(
                    title="卖出信号确认",
                    message=message,
                    on_confirm=lambda: self.logger.info(f"用户确认准备卖出: {bond_code}")
                )
                
                if not confirmed:
                    return jsonify({
                        'success': False, 
                        'error': '用户取消',
                        'message': '用户点击忽略或超时未响应'
                    }), 200
                
                success, msg = self.trader.prepare_sell_order(bond_code, bond_name, price, lots)
                
                if success:
                    self.logger.info(f"卖出准备成功: {bond_code} {lots}手 @ {price}")
                    return jsonify({
                        'success': True,
                        'message': msg,
                        'data': {
                            'code': bond_code,
                            'name': bond_name,
                            'price': price,
                            'lots': lots,
                            'quantity': quantity,
                            'amount': round(amount, 2),
                            'side': 'sell'
                        }
                    })
                else:
                    self.logger.warning(f"卖出准备失败: {msg}")
                    return jsonify({
                        'success': False,
                        'error': msg
                    }), 400
                    
            except Exception as e:
                self.logger.error(f"卖出准备异常: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/status', methods=['GET'])
        def api_status():
            """获取当前状态"""
            try:
                status = self.trader.get_status()
                return jsonify({
                    'success': True,
                    'data': status
                })
            except Exception as e:
                self.logger.error(f"获取状态异常: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/connect', methods=['POST'])
        def api_connect():
            """连接华泰软件"""
            try:
                success = self.trader.connect()
                if success:
                    self.logger.info("连接华泰软件成功")
                    return jsonify({
                        'success': True,
                        'message': '已连接到华泰交易软件'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': '无法连接或启动华泰软件'
                    }), 500
            except Exception as e:
                self.logger.error(f"连接异常: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/health', methods=['GET'])
        def api_health():
            """健康检查"""
            return jsonify({
                'status': 'ok',
                'timestamp': datetime.now().isoformat()
            })
    
    def run(self):
        """启动服务"""
        host = self.config['http_server']['host']
        port = self.config['http_server']['port']
        
        self.logger.info(f"=" * 50)
        self.logger.info(f"华泰交易助手服务启动")
        self.logger.info(f"监听地址: http://{host}:{port}")
        self.logger.info(f"=" * 50)
        
        # 禁用Flask默认的启动信息
        import click
        def secho(text, file=None, nl=None, err=None, color=None, **styles):
            pass
        def echo(text, file=None, nl=None, err=None, color=None, **styles):
            pass
        click.echo = echo
        click.secho = secho
        
        self.app.run(host=host, port=port, debug=False, use_reloader=False)


def start_server(config_path: str = None):
    """启动服务的入口函数"""
    server = TradeServer(config_path)
    server.run()


if __name__ == '__main__':
    start_server()
