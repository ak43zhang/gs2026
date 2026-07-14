"""
华泰交易助手核心模块
负责窗口连接和委托单填充（不点击买入按钮）
"""

import time
import logging
from pathlib import Path
from typing import Optional, Tuple
import yaml

try:
    from pywinauto import Application
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
    
    核心功能：
    1. 连接华泰交易软件窗口
    2. 填充买入委托信息（不点击买入按钮）
    3. 填充卖出委托信息（不点击卖出按钮）
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
    
    def connect(self) -> Tuple[bool, str]:
        """
        连接华泰交易软件窗口（通过进程路径连接）
        
        Returns:
            (是否成功, 消息)
        """
        try:
            win_config = self.config.get('window_config', {})
            exe_path = win_config.get('exe_path', r'D:\华泰证券网上交易委托系统\xiadan.exe')
            title = win_config.get('main_window_title', '网上股票交易系统5.0')
            backend = win_config.get('backend', 'win32')
            
            # 通过进程路径连接（兼容32位软件）
            self.app = Application(backend=backend).connect(
                path=exe_path,
                timeout=5
            )
            
            # 定位主窗口
            self.main_window = self.app.window(title=title)
            
            # 验证窗口存在
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
        """检查是否已连接（仅检查标志，不跨线程验证窗口）"""
        return self._connected and self.main_window is not None
    
    def is_trading_time(self) -> bool:
        """检查是否在交易时段"""
        from datetime import datetime
        now = datetime.now()
        hour, minute = now.hour, now.minute
        t = hour * 100 + minute
        return (930 <= t <= 1130) or (1300 <= t <= 1500)
    
    def get_trading_status(self) -> str:
        """获取交易状态描述"""
        from datetime import datetime
        now = datetime.now()
        return f"{now.strftime('%H:%M')} (交易时段: 09:30-11:30, 13:00-15:00)"
    
    def prepare_buy_order(self, bond_code: str, bond_name: str, 
                          price: float, lots: int = 1) -> Tuple[bool, str]:
        """
        准备买入委托（填充信息，不点击买入按钮）
        
        Args:
            bond_code: 债券代码（6位）
            bond_name: 债券名称
            price: 委托价格
            lots: 手数（1手=10张）
            
        Returns:
            (是否成功, 消息)
        """
        # 检查连接
        if not self.is_connected():
            success, msg = self.connect()
            if not success:
                return False, f"未连接华泰软件: {msg}"
        
        try:
            win_config = self.config.get('window_config', {})
            buy_controls = win_config.get('buy_controls', {})
            
            # 获取控件标识
            code_id = buy_controls.get('code_input', '证券代码Edit')
            price_id = buy_controls.get('price_input', '买入价格Edit')
            quantity_id = buy_controls.get('quantity_input', '买入数量Edit')
            
            # 确保窗口在前台
            self.main_window.set_focus()
            time.sleep(0.3)
            
            # 先点击"买入股票"标签确保在买入面板
            try:
                buy_tab = self.main_window.child_window(title="买入股票", class_name="Static")
                if buy_tab.exists():
                    buy_tab.click_input()
                    time.sleep(0.2)
            except:
                pass  # 如果已在买入面板，忽略
            
            # 填充证券代码
            code_edit = self.main_window[code_id]
            code_edit.set_focus()
            code_edit.set_edit_text(bond_code)
            time.sleep(0.5)  # 等待软件查询债券信息
            
            # 填充价格
            price_edit = self.main_window[price_id]
            price_edit.set_focus()
            price_edit.set_edit_text(f"{price:.3f}")
            time.sleep(0.1)
            
            # 填充数量（手数转张数）
            quantity = lots * 10
            qty_edit = self.main_window[quantity_id]
            qty_edit.set_focus()
            qty_edit.set_edit_text(str(quantity))
            time.sleep(0.1)
            
            logger.info(f"买入填充完成: {bond_code} {bond_name} {price}元 {lots}手({quantity}张)")
            return True, f"已填充: {bond_code} {bond_name} {price}元 {lots}手"
            
        except Exception as e:
            logger.error(f"买入填充失败: {e}")
            return False, f"填充失败: {e}"
    
    def prepare_sell_order(self, bond_code: str, bond_name: str, 
                           price: float, lots: int = 1) -> Tuple[bool, str]:
        """
        准备卖出委托（填充信息，不点击卖出按钮）
        """
        if not self.is_connected():
            success, msg = self.connect()
            if not success:
                return False, f"未连接华泰软件: {msg}"
        
        try:
            win_config = self.config.get('window_config', {})
            sell_controls = win_config.get('sell_controls', {})
            
            code_id = sell_controls.get('code_input', '证券代码Edit')
            price_id = sell_controls.get('price_input', '卖出价格Edit')
            quantity_id = sell_controls.get('quantity_input', '卖出数量Edit')
            
            # 确保窗口在前台
            self.main_window.set_focus()
            time.sleep(0.3)
            
            # 点击"卖出股票"标签切换到卖出面板
            try:
                sell_tab = self.main_window.child_window(title="卖出股票", class_name="Static")
                if sell_tab.exists():
                    sell_tab.click_input()
                    time.sleep(0.2)
            except:
                pass
            
            # 填充证券代码
            code_edit = self.main_window[code_id]
            code_edit.set_focus()
            code_edit.set_edit_text(bond_code)
            time.sleep(0.5)
            
            # 填充价格
            price_edit = self.main_window[price_id]
            price_edit.set_focus()
            price_edit.set_edit_text(f"{price:.3f}")
            time.sleep(0.1)
            
            # 填充数量
            quantity = lots * 10
            qty_edit = self.main_window[quantity_id]
            qty_edit.set_focus()
            qty_edit.set_edit_text(str(quantity))
            time.sleep(0.1)
            
            logger.info(f"卖出填充完成: {bond_code} {bond_name} {price}元 {lots}手({quantity}张)")
            return True, f"已填充: {bond_code} {bond_name} {price}元 {lots}手"
            
        except Exception as e:
            logger.error(f"卖出填充失败: {e}")
            return False, f"填充失败: {e}"
