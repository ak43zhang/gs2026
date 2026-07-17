"""
成交弹窗交互式探测

使用方法:
    1. 运行脚本
    2. 在华泰执行买入
    3. 弹窗出现后,鼠标移到弹窗上
    4. 回到脚本窗口按Enter
    5. 脚本会分析鼠标下的窗口成分

原理:
    通过鼠标位置获取窗口句柄,然后使用UIA分析窗口结构
"""

import time
import ctypes
import ctypes.wintypes
from ctypes import windll, byref, WINFUNCTYPE
from datetime import datetime
from pathlib import Path
import json


def get_mouse_pos():
    """获取鼠标位置"""
    pt = ctypes.wintypes.POINT()
    windll.user32.GetCursorPos(byref(pt))
    return pt.x, pt.y


def get_window_at_mouse():
    """获取鼠标下的窗口句柄"""
    pt = ctypes.wintypes.POINT()
    windll.user32.GetCursorPos(byref(pt))
    
    # WindowFromPoint 获取鼠标下的窗口
    hwnd = windll.user32.WindowFromPoint(pt)
    return hwnd


def get_window_info(hwnd):
    """获取窗口信息"""
    info = {'hwnd': hwnd}
    
    # 标题
    length = windll.user32.GetWindowTextLengthW(hwnd)
    if length > 0:
        buf = ctypes.create_unicode_buffer(length + 1)
        windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        info['title'] = buf.value
    else:
        info['title'] = "(无标题)"
    
    # 类名
    cls_buf = ctypes.create_unicode_buffer(256)
    windll.user32.GetClassNameW(hwnd, cls_buf, 256)
    info['class'] = cls_buf.value
    
    # 位置和大小
    rect = ctypes.wintypes.RECT()
    windll.user32.GetWindowRect(hwnd, byref(rect))
    info['rect'] = {
        'left': rect.left,
        'top': rect.top,
        'right': rect.right,
        'bottom': rect.bottom,
        'width': rect.right - rect.left,
        'height': rect.bottom - rect.top,
    }
    
    # 是否可见
    info['visible'] = bool(windll.user32.IsWindowVisible(hwnd))
    
    # 父窗口
    parent = windll.user32.GetParent(hwnd)
    info['parent_hwnd'] = parent
    
    return info


def get_parent_chain(hwnd, max_depth=5):
    """获取父窗口链"""
    chain = []
    current = hwnd
    
    for i in range(max_depth):
        info = get_window_info(current)
        chain.append(info)
        
        parent = windll.user32.GetParent(current)
        if not parent or parent == current:
            break
        current = parent
    
    return chain


def analyze_with_pywinauto(hwnd):
    """使用pywinauto分析窗口"""
    try:
        from pywinauto import Desktop
        
        # 连接到桌面
        desktop = Desktop(backend="uia")
        
        # 尝试找到这个窗口
        try:
            window = desktop.window(handle=hwnd)
            
            analysis = {
                'found': True,
                'control_type': window.element_info.control_type,
                'name': window.element_info.name,
                'automation_id': window.element_info.automation_id,
                'class_name': window.element_info.class_name,
            }
            
            # 获取所有子控件
            children = window.children()
            analysis['children_count'] = len(children)
            analysis['children'] = []
            
            for child in children[:20]:  # 只取前20个
                try:
                    child_info = {
                        'control_type': child.element_info.control_type,
                        'name': child.element_info.name,
                        'automation_id': child.element_info.automation_id,
                    }
                    analysis['children'].append(child_info)
                except:
                    pass
            
            # 获取窗口文本
            try:
                all_texts = window.texts()
                analysis['texts'] = all_texts
            except:
                analysis['texts'] = []
            
            return analysis
            
        except Exception as e:
            return {'found': False, 'error': str(e)}
            
    except ImportError:
        return {'found': False, 'error': 'pywinauto未安装'}


def get_process_info(hwnd):
    """获取窗口所属进程信息"""
    try:
        # 获取进程ID
        pid = ctypes.wintypes.DWORD()
        windll.user32.GetWindowThreadProcessId(hwnd, byref(pid))
        
        # 打开进程
        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_VM_READ = 0x0010
        
        h_process = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
            False,
            pid.value
        )
        
        if h_process:
            # 获取进程名
            exe_name = ctypes.create_unicode_buffer(512)
            ctypes.windll.psapi.GetModuleBaseNameW(
                h_process, None, exe_name, 512
            )
            
            ctypes.windll.kernel32.CloseHandle(h_process)
            
            return {
                'pid': pid.value,
                'exe': exe_name.value,
            }
    except:
        pass
    
    return {'pid': None, 'exe': 'unknown'}


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  成交弹窗交互式探测                                              ║
║                                                                  ║
║  使用方法:                                                       ║
║  1. 运行脚本                                                      ║
║  2. 在华泰执行买入                                               ║
║  3. 弹窗出现后,鼠标移到弹窗上                                    ║
║  4. 回到脚本窗口按Enter                                          ║
║  5. 脚本会分析鼠标下的窗口成分                                    ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    print("\n  等待您按Enter...")
    print("  (请先将鼠标移到弹窗上,然后回来按Enter)")
    input()
    
    # 获取鼠标位置
    mouse_x, mouse_y = get_mouse_pos()
    print(f"\n  鼠标位置: ({mouse_x}, {mouse_y})")
    
    # 获取鼠标下的窗口
    hwnd = get_window_at_mouse()
    print(f"  窗口句柄: {hwnd}")
    
    if not hwnd:
        print("  ❌ 未找到窗口")
        return
    
    # 获取窗口基本信息
    print("\n" + "="*60)
    print("  窗口基本信息 (Win32 API)")
    print("="*60)
    
    info = get_window_info(hwnd)
    print(f"  标题: {info['title']}")
    print(f"  类名: {info['class']}")
    print(f"  句柄: {info['hwnd']}")
    print(f"  可见: {info['visible']}")
    print(f"  位置: ({info['rect']['left']}, {info['rect']['top']})")
    print(f"  大小: {info['rect']['width']}x{info['rect']['height']}")
    
    # 获取进程信息
    proc_info = get_process_info(hwnd)
    print(f"  进程ID: {proc_info['pid']}")
    print(f"  进程名: {proc_info['exe']}")
    
    # 获取父窗口链
    print("\n" + "="*60)
    print("  父窗口链")
    print("="*60)
    
    chain = get_parent_chain(hwnd)
    for i, win in enumerate(chain):
        indent = "  " * i
        print(f"{indent}[{i}] {win['title'][:40]} (类名: {win['class']})")
    
    # 使用pywinauto分析
    print("\n" + "="*60)
    print("  UIA 详细分析 (pywinauto)")
    print("="*60)
    
    analysis = analyze_with_pywinauto(hwnd)
    
    if analysis.get('found'):
        print(f"  控件类型: {analysis.get('control_type')}")
        print(f"  名称: {analysis.get('name')}")
        print(f"  Automation ID: {analysis.get('automation_id')}")
        print(f"  类名: {analysis.get('class_name')}")
        print(f"  子控件数: {analysis.get('children_count')}")
        
        print("\n  子控件列表 (前20个):")
        for child in analysis.get('children', []):
            print(f"    - [{child.get('control_type')}] \"{child.get('name', '')[:30]}\"")
        
        print("\n  窗口文本内容:")
        for text in analysis.get('texts', [])[:10]:
            if text.strip():
                print(f"    \"{text[:60]}\"")
    else:
        print(f"  分析失败: {analysis.get('error')}")
    
    # 保存结果
    result = {
        'timestamp': datetime.now().isoformat(),
        'mouse_pos': {'x': mouse_x, 'y': mouse_y},
        'win32_info': info,
        'process_info': proc_info,
        'parent_chain': chain,
        'uia_analysis': analysis,
    }
    
    output_file = Path(__file__).parent / "popup_interactive_result.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n  结果已保存: {output_file}")
    
    # 给出建议
    print("\n" + "="*60)
    print("  分析建议")
    print("="*60)
    
    if analysis.get('found'):
        title = analysis.get('name', '')
        
        if '成交' in title or '回报' in title:
            print(f"\n  ✓ 这看起来是成交弹窗!")
            print(f"    标题: {title}")
            print(f"    控件类型: {analysis.get('control_type')}")
            
            print(f"\n  监听代码示例:")
            print(f"    from pywinauto import Application")
            print(f"    app = Application(backend='uia').connect(title_re='网上股票交易系统5.0')")
            print(f"    popup = app.window(title='{title}', control_type='Window')")
            print(f"    if popup.exists():")
            print(f"        texts = popup.texts()")
            print(f"        # 解析成交信息")
            
        else:
            print(f"\n  ? 不确定是否是成交弹窗")
            print(f"    标题: {title}")
            print(f"    建议检查是否匹配")
    
    print("\n  下一步:")
    print("    1. 查看 popup_interactive_result.json 完整信息")
    print("    2. 根据控件类型和标题更新检测逻辑")
    print("    3. 测试自动检测")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n  错误: {e}")
        import traceback
        traceback.print_exc()
    
    input("\n  按Enter退出...")
