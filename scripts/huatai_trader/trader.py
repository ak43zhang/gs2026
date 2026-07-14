"""
华泰交易助手核心模块
负责窗口操作和委托单准备
"""

import time
import datetime
import winsound
from pathlib import Path
from typing import Optional, Tuple
import yaml

# pywinauto用于Windows窗口操作
try:
    from pywinauto import Application, Desktop
    from pywinauto.keyboard import send_keys
    from pywinauto.mouse import click
except ImportError:
    raise ImportError("请先安装 pywinauto: pip install pywinauto")


class HuaTaiTrader:
    """
    华泰证券可转债半自动交易助手
    
    核心功能：
    1. 连接/启动华泰交易软件
    2. 准备买入委托单（填充信息，不提交）
    3. 准备卖出委托单（填充信息，不提交）
    4. 风控检查
    """
    
    def __init__(self, config_path: str = None):
        """初始化交易助手"""
        if config_path is None:
            config_path = Path(__file__).parent / "配置.yaml"
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        self.app = None
        self.main_window = None
        self.daily_stats = {
            'preparation_count': 0,
            'total_amount': 0.0,
            'consecutive_failures': 0,
            'last_bond_code': None,
            'last_preparation_time': None
        }
        
        # 风控状态
        self.is_fuse_tripped = False
        self.fuse_reset_time = None
        
    # ==================== 连接管理 ====================
    
    def connect(self) -> bool:
        """
        连接已运行的华泰软件，或启动新实例
        
        Returns:
            bool: 是否成功连接
        """
        try:
            # 先尝试连接已运行的实例
            desktop = Desktop(backend="win32")
            for window in desktop.windows():
                title = window.window_text()
                if any(keyword in title for keyword in self.config['window_config']['main_window_title_keywords']):
                    self.main_window = window
                    print(f"[CONNECT] 已连接到运行中的窗口: {title}")
                    return True
            
            # 未找到，启动新实例
            shortcut = self.config['window_config']['shortcut_path']
            if Path(shortcut).exists():
                import os
                os.startfile(shortcut)
                print(f"[CONNECT] 正在启动华泰证券软件...")
                time.sleep(5)  # 等待启动
                
                # 重新查找窗口
                for window in desktop.windows():
                    title = window.window_text()
                    if any(keyword in title for keyword in self.config['window_config']['main_window_title_keywords']):
                        self.main_window = window
                        print(f"[CONNECT] 已启动并连接到: {title}")
                        return True
            
            print("[ERROR] 无法连接或启动华泰证券软件")
            return False
            
        except Exception as e:
            print(f"[ERROR] 连接失败: {e}")
            return False
    
    # ==================== 交易时段检查 ====================
    
    def is_trading_time(self) -> bool:
        """
        检查当前是否在交易时段内
        
        Returns:
            bool: 是否在交易时段
        """
        now = datetime.datetime.now()
        current_time = now.strftime("%H:%M")
        
        morning_start = self.config['trading_hours']['morning_session']['start_time']
        morning_end = self.config['trading_hours']['morning_session']['end_time']
        afternoon_start = self.config['trading_hours']['afternoon_session']['start_time']
        afternoon_end = self.config['trading_hours']['afternoon_session']['end_time']
        
        is_morning = morning_start <= current_time <= morning_end
        is_afternoon = afternoon_start <= current_time <= afternoon_end
        
        return is_morning or is_afternoon
    
    def get_trading_status(self) -> str:
        """获取当前交易时段状态描述"""
        if self.is_trading_time():
            return "交易中"
        
        now = datetime.datetime.now()
        current_time = now.strftime("%H:%M")
        morning_start = self.config['trading_hours']['morning_session']['start_time']
        afternoon_end = self.config['trading_hours']['afternoon_session']['end_time']
        
        if current_time < morning_start:
            return "盘前"
        elif current_time > afternoon_end:
            return "盘后"
        else:
            return "午间休市"
    
    # ==================== 风控检查 ====================
    
    def check_risk_limits(self, bond_code: str, price: float, lots: int) -> Tuple[bool, str]:
        """
        检查风控限额
        
        Args:
            bond_code: 债券代码
            price: 委托价格
            lots: 手数
            
        Returns:
            (是否通过, 失败原因)
        """
        # 检查熔断状态
        if self.is_fuse_tripped:
            if self.fuse_reset_time and datetime.datetime.now() < self.fuse_reset_time:
                remaining = (self.fuse_reset_time - datetime.datetime.now()).seconds // 60
                return False, f"风控熔断中，剩余冷却时间: {remaining}分钟"
            else:
                # 重置熔断
                self.is_fuse_tripped = False
                self.fuse_reset_time = None
                self.daily_stats['consecutive_failures'] = 0
        
        # 检查交易时段
        if not self.is_trading_time():
            if not self.config['trading_hours']['allow_preparation_after_hours']:
                return False, f"非交易时段: {self.get_trading_status()}"
        
        # 检查单日最大准备次数
        max_preparations = self.config['risk_control']['max_daily_order_preparations']
        if self.daily_stats['preparation_count'] >= max_preparations:
            return False, f"已达到单日最大准备次数: {max_preparations}"
        
        # 计算金额
        quantity = lots * 10  # 手数转张数
        amount = quantity * price
        
        # 检查单笔金额
        min_amount = self.config['risk_control']['min_single_order_amount']
        max_amount = self.config['risk_control']['max_single_order_amount']
        if amount < min_amount:
            return False, f"单笔金额({amount:.2f})低于最小限额({min_amount})"
        if amount > max_amount:
            return False, f"单笔金额({amount:.2f})超过最大限额({max_amount})"
        
        # 检查价格范围
        price_range = self.config['risk_control']['bond_price_range']
        if price < price_range['min_price'] or price > price_range['max_price']:
            return False, f"价格({price})超出有效范围({price_range['min_price']}-{price_range['max_price']})"
        
        # 检查同一债券间隔
        min_interval = self.config['risk_control']['min_interval_same_bond_seconds']
        if (self.daily_stats['last_bond_code'] == bond_code and 
            self.daily_stats['last_preparation_time'] is not None):
            elapsed = (datetime.datetime.now() - self.daily_stats['last_preparation_time']).total_seconds()
            if elapsed < min_interval:
                return False, f"同一债券准备间隔过短，还需等待{min_interval - elapsed:.0f}秒"
        
        return True, "OK"
    
    def record_failure(self):
        """记录失败，检查是否触发熔断"""
        self.daily_stats['consecutive_failures'] += 1
        max_failures = self.config['risk_control']['max_consecutive_preparation_failures']
        
        if self.daily_stats['consecutive_failures'] >= max_failures:
            self.is_fuse_tripped = True
            cooldown = self.config['risk_control']['failure_cooldown_minutes']
            self.fuse_reset_time = datetime.datetime.now() + datetime.timedelta(minutes=cooldown)
            print(f"[RISK] 连续失败{max_failures}次，触发熔断，冷却{cooldown}分钟")
    
    def record_success(self, bond_code: str, amount: float):
        """记录成功"""
        self.daily_stats['consecutive_failures'] = 0
        self.daily_stats['preparation_count'] += 1
        self.daily_stats['total_amount'] += amount
        self.daily_stats['last_bond_code'] = bond_code
        self.daily_stats['last_preparation_time'] = datetime.datetime.now()
    
    # ==================== 委托单准备 ====================
    
    def prepare_buy_order(self, bond_code: str, bond_name: str, price: float, 
                         lots: int = None) -> Tuple[bool, str]:
        """
        准备买入委托单
        
        Args:
            bond_code: 债券代码，如"123257"
            bond_name: 债券名称，如"美诺转债"
            price: 买入价格
            lots: 买入手数，默认从配置读取
            
        Returns:
            (是否成功, 消息)
        """
        if lots is None:
            lots = self.config['convertible_bond']['default_buy_lots']
        
        # 风控检查
        passed, reason = self.check_risk_limits(bond_code, price, lots)
        if not passed:
            return False, f"风控拦截: {reason}"
        
        try:
            # 确保已连接
            if not self.main_window:
                if not self.connect():
                    self.record_failure()
                    return False, "无法连接华泰软件"
            
            # 激活买入窗口
            if not self._activate_buy_window():
                self.record_failure()
                return False, "无法激活买入窗口"
            
            # 填写委托信息
            quantity = lots * 10  # 手数转张数
            self._fill_order_form(bond_code, quantity, price)
            
            # 计算金额
            amount = quantity * price
            self.record_success(bond_code, amount)
            
            # 播放提示音
            if self.config['user_interface']['sound_alert']:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            
            return True, f"买入委托已准备: {bond_name}({bond_code}) {lots}手 @ {price}元，请确认提交"
            
        except Exception as e:
            self.record_failure()
            return False, f"准备买入失败: {e}"
    
    def prepare_sell_order(self, bond_code: str, bond_name: str, price: float,
                          lots: int = None) -> Tuple[bool, str]:
        """
        准备卖出委托单
        
        Args:
            bond_code: 债券代码
            bond_name: 债券名称
            price: 卖出价格
            lots: 卖出手数
            
        Returns:
            (是否成功, 消息)
        """
        if lots is None:
            lots = self.config['convertible_bond']['default_buy_lots']
        
        # 风控检查
        passed, reason = self.check_risk_limits(bond_code, price, lots)
        if not passed:
            return False, f"风控拦截: {reason}"
        
        try:
            # 确保已连接
            if not self.main_window:
                if not self.connect():
                    self.record_failure()
                    return False, "无法连接华泰软件"
            
            # 激活卖出窗口
            if not self._activate_sell_window():
                self.record_failure()
                return False, "无法激活卖出窗口"
            
            # 填写委托信息
            quantity = lots * 10
            self._fill_order_form(bond_code, quantity, price)
            
            # 计算金额
            amount = quantity * price
            self.record_success(bond_code, amount)
            
            # 播放提示音
            if self.config['user_interface']['sound_alert']:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            
            return True, f"卖出委托已准备: {bond_name}({bond_code}) {lots}手 @ {price}元，请确认提交"
            
        except Exception as e:
            self.record_failure()
            return False, f"准备卖出失败: {e}"
    
    # ==================== 窗口操作（内部方法） ====================
    
    def _activate_buy_window(self) -> bool:
        """激活买入窗口"""
        try:
            # 先激活主窗口
            self.main_window.set_focus()
            time.sleep(0.3)
            
            # 查找买入窗口
            desktop = Desktop(backend="win32")
            for window in desktop.windows():
                title = window.window_text()
                if any(keyword in title for keyword in self.config['window_config']['buy_window_title_keywords']):
                    window.set_focus()
                    time.sleep(0.2)
                    return True
            
            # 未找到，尝试通过菜单或快捷键打开
            # 这里需要根据实际软件界面调整
            print("[WARN] 未找到买入窗口，尝试通过主窗口操作")
            return True
            
        except Exception as e:
            print(f"[ERROR] 激活买入窗口失败: {e}")
            return False
    
    def _activate_sell_window(self) -> bool:
        """激活卖出窗口"""
        try:
            self.main_window.set_focus()
            time.sleep(0.3)
            
            desktop = Desktop(backend="win32")
            for window in desktop.windows():
                title = window.window_text()
                if any(keyword in title for keyword in self.config['window_config']['sell_window_title_keywords']):
                    window.set_focus()
                    time.sleep(0.2)
                    return True
            
            print("[WARN] 未找到卖出窗口，尝试通过主窗口操作")
            return True
            
        except Exception as e:
            print(f"[ERROR] 激活卖出窗口失败: {e}")
            return False
    
    def _fill_order_form(self, code: str, quantity: int, price: float):
        """
        填写委托表单
        
        注意：控件名称需要根据实际软件版本调整
        """
        try:
            # 获取当前活动窗口
            active_window = self.main_window
            
            # 使用快捷键或控件操作填充
            # 方案1: 使用Tab键切换焦点后输入
            # 方案2: 直接操作控件（需要知道控件名）
            
            # 这里使用方案1（通用但依赖界面布局）
            # 实际使用时需要根据Inspect工具获取的控件信息调整
            
            # 清除并输入代码
            send_keys("^a")  # Ctrl+A 全选
            time.sleep(0.1)
            send_keys(code)
            time.sleep(0.2)
            
            # 切换到数量输入框（Tab键）
            send_keys("{TAB}")
            time.sleep(0.1)
            send_keys("^a")
            time.sleep(0.1)
            send_keys(str(quantity))
            time.sleep(0.2)
            
            # 切换到价格输入框
            send_keys("{TAB}")
            time.sleep(0.1)
            send_keys("^a")
            time.sleep(0.1)
            send_keys(str(price))
            time.sleep(0.2)
            
            print(f"[FILL] 已填写: 代码={code}, 数量={quantity}, 价格={price}")
            
        except Exception as e:
            print(f"[ERROR] 填写表单失败: {e}")
            raise
    
    # ==================== 状态查询 ====================
    
    def get_status(self) -> dict:
        """获取当前状态"""
        return {
            'connected': self.main_window is not None,
            'trading_status': self.get_trading_status(),
            'is_trading_time': self.is_trading_time(),
            'daily_preparations': self.daily_stats['preparation_count'],
            'daily_amount': self.daily_stats['total_amount'],
            'consecutive_failures': self.daily_stats['consecutive_failures'],
            'is_fuse_tripped': self.is_fuse_tripped
        }
