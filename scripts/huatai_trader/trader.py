"""
华泰交易助手核心模块
使用纯键盘驱动方式填充委托单（F1买入/F2卖出 + Tab切换字段）
不依赖控件名称查找，避免叠层面板定位错误
"""

import time
import logging
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
    - 不使用控件名称查找（华泰买入/卖出面板控件位置重叠，名称查找不可靠）
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
    
    def connect(self) -> Tuple[bool, str]:
        """
        连接华泰交易软件窗口（通过进程路径）
        """
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
    
    def prepare_buy_order(self, bond_code: str, bond_name: str, 
                          price: float, lots: int = 1) -> Tuple[bool, str]:
        """
        准备买入委托（键盘驱动，填充信息不点击买入按钮）
        
        流程：
        1. 激活窗口
        2. F1 切到买入面板（焦点自动落在代码框）
        3. 输入代码 → 等待查询
        4. Tab到价格框 → 输入价格
        5. Tab到数量框 → 输入数量
        
        Args:
            bond_code: 债券代码（6位）
            bond_name: 债券名称
            price: 委托价格
            lots: 手数（1手=10张）
        """
        success, msg = self._ensure_connected()
        if not success:
            return False, f"未连接华泰软件: {msg}"
        
        try:
            quantity = lots * 10  # 手数转张数
            
            # 1. 激活窗口
            self._activate_window()
            
            # 2. F1切到买入面板（焦点自动到代码框）
            send_keys('{F1}')
            time.sleep(0.5)
            
            # 3. 填充代码（全选后输入）
            send_keys('^a')
            send_keys(bond_code, pause=0.05)
            time.sleep(1.0)  # 等待软件查询债券信息
            
            # 4. Tab到价格框，填充价格
            send_keys('{TAB}')
            time.sleep(0.1)
            send_keys('^a')
            send_keys(f'{price:.3f}', pause=0.05)
            
            # 5. Tab到数量框，填充数量
            send_keys('{TAB}')
            time.sleep(0.1)
            send_keys('^a')
            send_keys(str(quantity), pause=0.05)
            
            logger.info(f"买入填充完成: {bond_code} {bond_name} {price}元 {lots}手({quantity}张)")
            return True, f"已填充买入: {bond_code} {bond_name} {price}元 {lots}手"
            
        except Exception as e:
            logger.error(f"买入填充失败: {e}")
            self._connected = False  # 标记断开，下次重连
            return False, f"填充失败: {e}"
    
    def prepare_sell_order(self, bond_code: str, bond_name: str, 
                           price: float, lots: int = 1) -> Tuple[bool, str]:
        """
        准备卖出委托（键盘驱动，填充信息不点击卖出按钮）
        
        流程：
        1. 激活窗口
        2. F2 切到卖出面板（焦点自动落在代码框）
        3. 输入代码 → 等待查询
        4. Tab到价格框 → 输入价格
        5. Tab到数量框 → 输入数量
        """
        success, msg = self._ensure_connected()
        if not success:
            return False, f"未连接华泰软件: {msg}"
        
        try:
            quantity = lots * 10
            
            # 1. 激活窗口
            self._activate_window()
            
            # 2. F2切到卖出面板
            send_keys('{F2}')
            time.sleep(0.5)
            
            # 3. 填充代码
            send_keys('^a')
            send_keys(bond_code, pause=0.05)
            time.sleep(1.0)
            
            # 4. Tab到价格框
            send_keys('{TAB}')
            time.sleep(0.1)
            send_keys('^a')
            send_keys(f'{price:.3f}', pause=0.05)
            
            # 5. Tab到数量框
            send_keys('{TAB}')
            time.sleep(0.1)
            send_keys('^a')
            send_keys(str(quantity), pause=0.05)
            
            logger.info(f"卖出填充完成: {bond_code} {bond_name} {price}元 {lots}手({quantity}张)")
            return True, f"已填充卖出: {bond_code} {bond_name} {price}元 {lots}手"
            
        except Exception as e:
            logger.error(f"卖出填充失败: {e}")
            self._connected = False
            return False, f"填充失败: {e}"
