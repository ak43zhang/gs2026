"""
华泰交易助手核心模块
使用纯键盘驱动方式填充委托单（F1买入/F2卖出 + Tab切换字段）
不依赖控件名称查找，避免叠层面板定位错误
"""

import time
import logging
import winsound
from pathlib import Path
from typing import Optional, Tuple
import yaml

try:
    from pywinauto import Application
    from pywinauto.keyboard import send_keys
    from pywinauto.timings import Timings
except ImportError:
    raise ImportError("请先安装 pywinauto: pip install pywinauto")


logger = logging.getLogger(__name__)

# 加快pywinauto操作速度
Timings.after_setfocus_wait = 0.1
Timings.after_setcursorpos_wait = 0.05


class HuaTaiTrader:
    """
    华泰证券可转债半自动交易助手
    
    核心设计：
    - 纯键盘驱动：F1切买入面板，F2切卖出面板，Tab切换字段
    - 默认只填证券代码，价格和数量由软件自动处理
    - 可配置填充价格和/或数量
    - 只填充信息，不点击买入/卖出按钮
    """
    
    def __init__(self, config_path: str = None):
        """初始化"""
        if config_path is None:
            config_path = Path(__file__).parent / "配置.yaml"
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        self.app: Optional[Application] = None
        self.main_window = None
        self._connected = False
        
        # 交易行为配置
        self.behavior = self.config.get('trading_behavior', {})
        self.price_mode = self.behavior.get('price_mode', 'auto')
        self.quantity_mode = self.behavior.get('quantity_mode', 'auto')
        self.default_quantity = self.behavior.get('default_quantity', 10)
        self.sound_enabled = self.behavior.get('sound_enabled', True)
    
    def connect(self) -> Tuple[bool, str]:
        """连接华泰交易软件窗口（通过进程路径）"""
        try:
            win_config = self.config.get('window_config', {})
            exe_path = win_config.get('exe_path', r'D:\华泰证券网上交易委托系统\xiadan.exe')
            title = win_config.get('main_window_title', '网上股票交易系统5.0')
            backend = win_config.get('backend', 'win32')
            
            self.app = Application(backend=backend).connect(
                path=exe_path,
                timeout=5
            )
            self.main_window = self.app.window(title=title)
            
            if self.main_window.exists():
                self._connected = True
                logger.info(f"已连接华泰交易窗口: {title}")
                return True, f"已连接: {title}"
            else:
                self._connected = False
                return False, f"进程已连接但未找到窗口: {title}"
                
        except Exception as e:
            self._connected = False
            return False, f"连接失败: {e}"
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected and self.main_window is not None
    
    def is_trading_time(self) -> bool:
        """检查是否在交易时段"""
        from datetime import datetime
        now = datetime.now()
        t = now.hour * 100 + now.minute
        return (930 <= t <= 1130) or (1300 <= t <= 1500)
    
    def get_trading_status(self) -> str:
        """获取交易状态描述"""
        from datetime import datetime
        now = datetime.now()
        return f"{now.strftime('%H:%M')} (交易时段: 09:30-11:30, 13:00-15:00)"
    
    def _ensure_connected(self) -> Tuple[bool, str]:
        """确保已连接，未连接则尝试重连"""
        if not self.is_connected():
            return self.connect()
        return True, "已连接"
    
    def _activate_window(self):
        """激活华泰主窗口"""
        self.main_window.set_focus()
        time.sleep(0.3)
    
    def _play_sound(self, success: bool):
        """播放提示音"""
        if not self.sound_enabled:
            return
        try:
            if success:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)  # 短促"叮"
            else:
                winsound.MessageBeep(winsound.MB_ICONHAND)  # 长"嘟"
        except:
            pass
    
    def prepare_buy_order(self, bond_code: str, bond_name: str = '',
                          price: float = None, lots: int = None) -> Tuple[bool, str]:
        """
        准备买入委托（键盘驱动）
        
        Args:
            bond_code: 证券代码（必填）
            bond_name: 名称（仅日志用）
            price: 价格（可选，显式传入时覆盖配置）
            lots: 手数（可选，显式传入时覆盖配置）
        """
        success, msg = self._ensure_connected()
        if not success:
            self._play_sound(False)
            return False, f"未连接华泰软件: {msg}"
        
        try:
            # 1. 激活窗口
            self._activate_window()
            
            # 2. F1切到买入面板（焦点自动到代码框）
            send_keys('{F1}')
            time.sleep(0.5)
            
            # 3. 填充代码（必填）
            send_keys('^a')
            send_keys(bond_code, pause=0.05)
            time.sleep(1.0)  # 等待软件查询债券信息
            
            # 4. 判断是否需要填充价格
            need_price = self._should_fill_price(price)
            need_quantity = self._should_fill_quantity(lots)
            
            if need_price:
                # Tab到价格框，填充价格
                send_keys('{TAB}')
                time.sleep(0.1)
                send_keys('^a')
                send_keys(f'{price:.3f}', pause=0.05)
                
                if need_quantity:
                    # Tab到数量框，填充数量
                    quantity = self._get_quantity(lots)
                    send_keys('{TAB}')
                    time.sleep(0.1)
                    send_keys('^a')
                    send_keys(str(quantity), pause=0.05)
            
            elif need_quantity:
                # 不填价格，但需要填数量：Tab跳过价格，到数量框
                quantity = self._get_quantity(lots)
                send_keys('{TAB}')  # 跳过价格
                time.sleep(0.1)
                send_keys('{TAB}')  # 到数量
                time.sleep(0.1)
                send_keys('^a')
                send_keys(str(quantity), pause=0.05)
            
            # 5. 播放成功提示音
            self._play_sound(True)
            
            # 构建日志信息
            detail = f"{bond_code}"
            if bond_name:
                detail += f" {bond_name}"
            if need_price:
                detail += f" @{price:.3f}"
            if need_quantity:
                detail += f" {self._get_quantity(lots)}张"
            
            logger.info(f"买入填充完成: {detail}")
            return True, f"已填充买入: {detail}"
            
        except Exception as e:
            self._play_sound(False)
            logger.error(f"买入填充失败: {e}")
            self._connected = False
            return False, f"填充失败: {e}"
    
    def prepare_sell_order(self, bond_code: str, bond_name: str = '',
                           price: float = None, lots: int = None) -> Tuple[bool, str]:
        """
        准备卖出委托（键盘驱动）
        
        Args:
            bond_code: 证券代码（必填）
            bond_name: 名称（仅日志用）
            price: 价格（可选）
            lots: 手数（可选）
        """
        success, msg = self._ensure_connected()
        if not success:
            self._play_sound(False)
            return False, f"未连接华泰软件: {msg}"
        
        try:
            # 1. 激活窗口
            self._activate_window()
            
            # 2. F2切到卖出面板
            send_keys('{F2}')
            time.sleep(0.5)
            
            # 3. 填充代码（必填）
            send_keys('^a')
            send_keys(bond_code, pause=0.05)
            time.sleep(1.0)
            
            # 4. 判断是否需要填充价格/数量
            need_price = self._should_fill_price(price)
            need_quantity = self._should_fill_quantity(lots)
            
            if need_price:
                send_keys('{TAB}')
                time.sleep(0.1)
                send_keys('^a')
                send_keys(f'{price:.3f}', pause=0.05)
                
                if need_quantity:
                    quantity = self._get_quantity(lots)
                    send_keys('{TAB}')
                    time.sleep(0.1)
                    send_keys('^a')
                    send_keys(str(quantity), pause=0.05)
            
            elif need_quantity:
                quantity = self._get_quantity(lots)
                send_keys('{TAB}')
                time.sleep(0.1)
                send_keys('{TAB}')
                time.sleep(0.1)
                send_keys('^a')
                send_keys(str(quantity), pause=0.05)
            
            # 5. 播放成功提示音
            self._play_sound(True)
            
            detail = f"{bond_code}"
            if bond_name:
                detail += f" {bond_name}"
            if need_price:
                detail += f" @{price:.3f}"
            if need_quantity:
                detail += f" {self._get_quantity(lots)}张"
            
            logger.info(f"卖出填充完成: {detail}")
            return True, f"已填充卖出: {detail}"
            
        except Exception as e:
            self._play_sound(False)
            logger.error(f"卖出填充失败: {e}")
            self._connected = False
            return False, f"填充失败: {e}"
    
    def _should_fill_price(self, price: float = None) -> bool:
        """判断是否需要填充价格"""
        # API显式传入price → 填充
        if price is not None:
            return True
        # 配置为manual但API没传 → 不填（没值可填）
        # 配置为auto → 不填
        return False
    
    def _should_fill_quantity(self, lots: int = None) -> bool:
        """判断是否需要填充数量"""
        # API显式传入lots → 填充
        if lots is not None:
            return True
        # 配置为fixed → 填充default_quantity
        if self.quantity_mode == 'fixed':
            return True
        # 配置为auto/manual但没传 → 不填
        return False
    
    def _get_quantity(self, lots: int = None) -> int:
        """获取实际填充的数量（张数）"""
        if lots is not None:
            return lots * 10  # 手数转张数
        # fixed模式使用配置值
        return self.default_quantity
