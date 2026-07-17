"""
止盈止损设置器 - 纯键盘驱动版本
不依赖坐标，完全使用键盘操作

特点:
- 窗口可以任意移动/缩放
- 不受DPI缩放影响
- 多显示器无问题
- 实现简单可靠

需要预先确认:
1. 华泰条件单的打开方式 (快捷键/菜单)
2. Tab导航顺序
"""

import time
import logging
import subprocess
import ctypes
from pathlib import Path
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class TpSlPlacerKeyboard:
    """
    纯键盘驱动的止盈止损条件单设置
    
    操作流程:
    1. 激活华泰窗口
    2. 打开条件单 (快捷键或菜单)
    3. 设置止盈条件单 (Tab导航)
    4. 设置止损条件单 (Tab导航)
    5. 提交 (可选自动或人工确认)
    """
    
    XIADAN_TITLE = "网上股票交易系统5.0"
    POPUP_TITLE = "华泰理财通"
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.use_shortcut = self.config.get('use_shortcut', True)
        self.auto_submit = self.config.get('auto_submit', False)
        
        # 配置按键序列 (需要根据实测调整)
        self.key_sequences = {
            'open_condition': ['^+c'],  # Ctrl+Shift+C (假设)
            'open_menu': ['%t', '{DOWN}{DOWN}{ENTER}'],  # Alt+T, 下下, Enter
        }
    
    # ==================== Win32 API 键盘操作 ====================
    
    def _send_keys(self, keys: str):
        """发送键盘按键"""
        try:
            from pywinauto.keyboard import send_keys
            send_keys(keys)
        except ImportError:
            # 备用: 使用ctypes直接发送
            self._send_keys_ctypes(keys)
    
    def _send_keys_ctypes(self, keys: str):
        """使用ctypes发送键盘事件 (备用)"""
        # 简化的实现，完整版需要解析keys字符串
        user32 = ctypes.windll.user32
        
        # 映射常见按键
        key_map = {
            '{TAB}': 0x09,
            '{ENTER}': 0x0D,
            '{ESC}': 0x1B,
            '{DOWN}': 0x28,
            '{UP}': 0x26,
            '{LEFT}': 0x25,
            '{RIGHT}': 0x27,
            '^a': (0x11, 0x41),  # Ctrl+A
        }
        
        if keys in key_map:
            vk = key_map[keys]
            if isinstance(vk, tuple):
                # 组合键
                user32.keybd_event(vk[0], 0, 0, 0)
                user32.keybd_event(vk[1], 0, 0, 0)
                time.sleep(0.02)
                user32.keybd_event(vk[1], 0, 2, 0)
                user32.keybd_event(vk[0], 0, 2, 0)
            else:
                # 单键
                user32.keybd_event(vk, 0, 0, 0)
                time.sleep(0.02)
                user32.keybd_event(vk, 0, 2, 0)
        
        time.sleep(0.1)
    
    def _type_text(self, text: str):
        """输入文本 (使用剪贴板)"""
        # 复制到剪贴板
        process = subprocess.Popen(['clip'], stdin=subprocess.PIPE, shell=True)
        process.communicate(text.encode('utf-16le'))
        time.sleep(0.05)
        
        # Ctrl+V 粘贴
        self._send_keys('^v')
    
    def _activate_window(self):
        """激活华泰窗口"""
        try:
            from pywinauto import Application
            app = Application(backend="win32").connect(
                path=r"D:\华泰证券网上交易委托系统\xiadan.exe",
                timeout=5
            )
            window = app.window(title=self.XIADAN_TITLE)
            window.set_focus()
            time.sleep(0.3)
            return True
        except Exception as e:
            logger.error(f"激活窗口失败: {e}")
            return False
    
    def _open_condition_order(self) -> bool:
        """
        打开条件单窗口
        
        方式1: 快捷键 (如果存在)
        方式2: 菜单导航 (Alt + 工具/条件单)
        
        Returns:
            是否成功打开
        """
        if self.use_shortcut:
            # 尝试快捷键方式
            try:
                # 假设快捷键是 Ctrl+Shift+C
                self._send_keys('^+c')
                time.sleep(0.5)
                
                # 检查弹窗是否出现
                if self._check_popup_exists():
                    logger.info("条件单窗口已打开 (快捷键)")
                    return True
            except Exception as e:
                logger.warning(f"快捷键打开失败: {e}")
        
        # 备用: 菜单导航
        try:
            # Alt + T (工具菜单)
            self._send_keys('%t')
            time.sleep(0.2)
            
            # 方向键选择条件单
            self._send_keys('{DOWN}{DOWN}{ENTER}')
            time.sleep(0.5)
            
            if self._check_popup_exists():
                logger.info("条件单窗口已打开 (菜单)")
                return True
                
        except Exception as e:
            logger.error(f"菜单打开失败: {e}")
        
        return False
    
    def _check_popup_exists(self) -> bool:
        """检查条件单弹窗是否存在"""
        try:
            import ctypes
            from ctypes import wintypes
            
            found = []
            
            @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            def cb(hwnd, lp):
                if ctypes.windll.user32.IsWindowVisible(hwnd):
                    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                        if self.POPUP_TITLE in buf.value:
                            found.append(hwnd)
                return True
            
            ctypes.windll.user32.EnumWindows(cb, 0)
            return len(found) > 0
            
        except Exception as e:
            logger.debug(f"检查弹窗失败: {e}")
            return False
    
    def _fill_condition_order(self, bond_code: str, trigger_price: float, 
                               order_price: float, quantity: int,
                               order_type: str = "止盈") -> bool:
        """
        填充条件单表单
        
        Args:
            bond_code: 债券代码
            trigger_price: 触发价
            order_price: 委托价
            quantity: 数量
            order_type: "止盈" 或 "止损"
            
        Returns:
            是否成功填充
        """
        try:
            # 填充代码 (假设当前焦点在代码框)
            self._send_keys('^a')  # 全选
            self._type_text(bond_code)
            time.sleep(0.1)
            self._send_keys('{TAB}')
            
            # 选择类型 (假设Tab到类型下拉框)
            if order_type == "止盈":
                self._send_keys('{DOWN}')  # 选择止盈
            else:
                self._send_keys('{DOWN}{DOWN}')  # 选择止损
            time.sleep(0.1)
            self._send_keys('{TAB}')
            
            # 填充触发价
            self._send_keys('^a')
            self._type_text(f"{trigger_price:.3f}")
            time.sleep(0.1)
            self._send_keys('{TAB}')
            
            # 填充委托价
            self._send_keys('^a')
            self._type_text(f"{order_price:.3f}")
            time.sleep(0.1)
            self._send_keys('{TAB}')
            
            # 填充数量
            self._send_keys('^a')
            self._type_text(str(quantity))
            time.sleep(0.1)
            
            logger.info(f"条件单表单已填充: {bond_code} {order_type}")
            return True
            
        except Exception as e:
            logger.error(f"填充表单失败: {e}")
            return False
    
    def _submit_order(self) -> bool:
        """
        提交条件单
        
        根据配置决定是否自动提交
        """
        if self.auto_submit:
            self._send_keys('{ENTER}')
            logger.info("条件单已自动提交")
            return True
        else:
            logger.info("条件单已填充，等待人工确认提交")
            # 播放提示音提醒用户
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except:
                pass
            return True
    
    # ==================== 公共接口 ====================
    
    def place(self, bond_code: str, base_price: float, 
              tp_pct: float, sl_pct: float, quantity: int) -> Dict:
        """
        设置止盈止损条件单
        
        Args:
            bond_code: 债券代码
            base_price: 基准价格 (买入价)
            tp_pct: 止盈百分比
            sl_pct: 止损百分比
            quantity: 数量
            
        Returns:
            {'success': bool, 'message': str}
        """
        try:
            # 1. 激活窗口
            if not self._activate_window():
                return {'success': False, 'message': '无法激活华泰窗口'}
            
            # 2. 计算止盈止损价格
            tp_price = base_price * (1 + tp_pct / 100)
            sl_price = base_price * (1 - sl_pct / 100)
            
            logger.info(f"设置止盈止损: {bond_code} TP={tp_price:.3f} SL={sl_price:.3f}")
            
            # 3. 设置止盈条件单
            if not self._open_condition_order():
                return {'success': False, 'message': '无法打开条件单窗口'}
            
            if not self._fill_condition_order(
                bond_code, tp_price, tp_price, quantity, "止盈"
            ):
                return {'success': False, 'message': '止盈条件单填充失败'}
            
            if not self._submit_order():
                return {'success': False, 'message': '止盈条件单提交失败'}
            
            # 4. 设置止损条件单
            time.sleep(0.5)
            
            if not self._open_condition_order():
                return {'success': False, 'message': '无法打开条件单窗口(止损)'}
            
            if not self._fill_condition_order(
                bond_code, sl_price, sl_price, quantity, "止损"
            ):
                return {'success': False, 'message': '止损条件单填充失败'}
            
            if not self._submit_order():
                return {'success': False, 'message': '止损条件单提交失败'}
            
            return {
                'success': True, 
                'message': f'止盈止损已设置 TP={tp_price:.3f} SL={sl_price:.3f}'
            }
            
        except Exception as e:
            logger.error(f"设置止盈止损异常: {e}", exc_info=True)
            return {'success': False, 'message': str(e)}


# ==================== 测试 ====================

if __name__ == '__main__':
    print("=" * 60)
    print("止盈止损键盘驱动测试")
    print("=" * 60)
    print()
    print("此测试需要在华泰软件打开的情况下运行")
    print("建议先用模拟交易测试")
    print()
    
    input("按Enter开始测试...")
    
    placer = TpSlPlacerKeyboard({
        'use_shortcut': True,
        'auto_submit': False,  # 测试时不自动提交
    })
    
    # 测试设置止盈止损
    result = placer.place(
        bond_code='127045',
        base_price=105.5,
        tp_pct=3.0,
        sl_pct=2.0,
        quantity=10
    )
    
    print(f"\n结果: {result}")
    
    if result['success']:
        print("\n✓ 测试通过")
        print("请检查华泰软件中的条件单是否正确设置")
    else:
        print(f"\n✗ 测试失败: {result['message']}")
        print("\n可能原因:")
        print("  1. 华泰软件未打开")
        print("  2. 快捷键不匹配")
        print("  3. Tab顺序不正确")
        print("\n建议:")
        print("  1. 在华泰中手动测试Tab顺序")
        print("  2. 调整代码中的按键序列")
