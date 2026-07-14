"""
交易确认弹窗模块
提供交易准备确认界面
"""

import tkinter as tk
from tkinter import ttk
import threading
import winsound
from typing import Callable


class TradeConfirmPopup:
    """
    交易确认弹窗
    
    功能：
    1. 显示交易信息
    2. 倒计时自动关闭
    3. 确认/取消操作
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.result = None
        self.root = None
        self.countdown = config.get('popup_timeout_seconds', 30)
        self.timer_label = None
        self.after_id = None
        
    def show(self, title: str, message: str, on_confirm: Callable = None, 
             on_cancel: Callable = None) -> bool:
        """
        显示确认弹窗
        
        Args:
            title: 窗口标题
            message: 显示信息
            on_confirm: 确认回调
            on_cancel: 取消回调
            
        Returns:
            用户是否点击确认
        """
        self.result = False
        
        # 创建窗口
        self.root = tk.Tk()
        self.root.title(title)
        
        # 设置窗口大小和位置
        width = self.config.get('popup_width', 400)
        height = self.config.get('popup_height', 250)
        
        # 获取屏幕尺寸
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # 根据配置设置位置
        position = self.config.get('popup_position', 'bottom_right')
        if position == 'bottom_right':
            x = screen_width - width - 20
            y = screen_height - height - 60
        elif position == 'top_right':
            x = screen_width - width - 20
            y = 20
        else:  # center
            x = (screen_width - width) // 2
            y = (screen_height - height) // 2
        
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.resizable(False, False)
        
        # 置顶显示
        self.root.attributes('-topmost', True)
        
        # 设置样式
        self.root.configure(bg='#f5f5f5')
        
        # 标题
        title_label = tk.Label(
            self.root,
            text="🔔 交易信号提醒",
            font=('Microsoft YaHei', 14, 'bold'),
            bg='#f5f5f5',
            fg='#333'
        )
        title_label.pack(pady=(15, 10))
        
        # 信息框
        info_frame = tk.Frame(self.root, bg='white', bd=1, relief='solid')
        info_frame.pack(padx=20, pady=10, fill='both', expand=True)
        
        info_label = tk.Label(
            info_frame,
            text=message,
            font=('Microsoft YaHei', 11),
            bg='white',
            fg='#333',
            justify='left',
            wraplength=width - 60
        )
        info_label.pack(padx=15, pady=15)
        
        # 倒计时标签
        self.timer_label = tk.Label(
            self.root,
            text=f"自动关闭倒计时: {self.countdown}秒",
            font=('Microsoft YaHei', 10),
            bg='#f5f5f5',
            fg='#e74c3c'
        )
        self.timer_label.pack(pady=(5, 10))
        
        # 按钮框
        btn_frame = tk.Frame(self.root, bg='#f5f5f5')
        btn_frame.pack(pady=(0, 15))
        
        # 确认按钮
        confirm_btn = tk.Button(
            btn_frame,
            text="准备委托",
            font=('Microsoft YaHei', 11, 'bold'),
            bg='#27ae60',
            fg='white',
            activebackground='#2ecc71',
            activeforeground='white',
            width=12,
            height=1,
            command=lambda: self._on_confirm(on_confirm)
        )
        confirm_btn.pack(side='left', padx=10)
        
        # 取消按钮
        cancel_btn = tk.Button(
            btn_frame,
            text="忽略",
            font=('Microsoft YaHei', 11),
            bg='#95a5a6',
            fg='white',
            activebackground='#7f8c8d',
            activeforeground='white',
            width=8,
            height=1,
            command=lambda: self._on_cancel(on_cancel)
        )
        cancel_btn.pack(side='left', padx=10)
        
        # 播放提示音
        if self.config.get('sound_alert', True):
            try:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except:
                pass
        
        # 启动倒计时
        self._update_countdown()
        
        # 运行窗口
        self.root.mainloop()
        
        return self.result
    
    def _update_countdown(self):
        """更新倒计时"""
        if self.countdown > 0 and self.root and self.timer_label:
            self.timer_label.config(text=f"自动关闭倒计时: {self.countdown}秒")
            self.countdown -= 1
            self.after_id = self.root.after(1000, self._update_countdown)
        else:
            # 倒计时结束，自动关闭
            self._on_cancel()
    
    def _on_confirm(self, callback: Callable = None):
        """确认按钮点击"""
        self.result = True
        if callback:
            callback()
        self._close()
    
    def _on_cancel(self, callback: Callable = None):
        """取消按钮点击或超时"""
        self.result = False
        if callback:
            callback()
        self._close()
    
    def _close(self):
        """关闭窗口"""
        if self.after_id:
            try:
                self.root.after_cancel(self.after_id)
            except:
                pass
        try:
            self.root.destroy()
        except:
            pass
        self.root = None


class QuickPopup:
    """
    快速提示弹窗（无交互，仅显示）
    """
    
    @staticmethod
    def show_info(title: str, message: str, duration: int = 3):
        """显示信息提示"""
        root = tk.Tk()
        root.title(title)
        root.attributes('-topmost', True)
        
        # 居中显示
        width, height = 300, 120
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        root.geometry(f"{width}x{height}+{x}+{y}")
        
        label = tk.Label(
            root,
            text=message,
            font=('Microsoft YaHei', 11),
            wraplength=280
        )
        label.pack(expand=True, padx=20, pady=20)
        
        # 自动关闭
        root.after(duration * 1000, root.destroy)
        root.mainloop()
    
    @staticmethod
    def show_error(title: str, message: str, duration: int = 5):
        """显示错误提示"""
        root = tk.Tk()
        root.title(title)
        root.attributes('-topmost', True)
        
        width, height = 350, 150
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        root.geometry(f"{width}x{height}+{x}+{y}")
        
        # 标题
        title_label = tk.Label(
            root,
            text="❌ 错误",
            font=('Microsoft YaHei', 12, 'bold'),
            fg='#e74c3c'
        )
        title_label.pack(pady=(15, 5))
        
        # 信息
        msg_label = tk.Label(
            root,
            text=message,
            font=('Microsoft YaHei', 10),
            wraplength=320,
            fg='#333'
        )
        msg_label.pack(pady=5)
        
        # 自动关闭
        root.after(duration * 1000, root.destroy)
        root.mainloop()
