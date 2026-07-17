"""
止盈止损条件单 - 信息采集脚本 v8
处理: 表单超出可视区域,需要滚动才能看到提交按钮
"""

import time
import sys
import json
import ctypes
from ctypes import windll, Structure, c_long, byref

class POINT(Structure):
    _fields_ = [("x", c_long), ("y", c_long)]

def get_mouse_pos():
    pt = POINT()
    windll.user32.GetCursorPos(byref(pt))
    return pt.x, pt.y

def get_window_at_mouse():
    pt = POINT()
    windll.user32.GetCursorPos(byref(pt))
    hwnd = windll.user32.WindowFromPoint(pt)
    root_hwnd = hwnd
    while True:
        parent = windll.user32.GetParent(root_hwnd)
        if parent == 0:
            break
        root_hwnd = parent
    length = windll.user32.GetWindowTextLengthW(root_hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    windll.user32.GetWindowTextW(root_hwnd, buf, length + 1)
    cls_buf = ctypes.create_unicode_buffer(256)
    windll.user32.GetClassNameW(root_hwnd, cls_buf, 256)
    return {
        'handle': root_hwnd,
        'title': buf.value,
        'class_name': cls_buf.value,
    }


def main():
    print("""
+======================================================+
|  止盈止损条件单 - 一键采集 v8                          |
|                                                      |
|  鼠标移到目标 -> 回这里按Enter -> 自动记录             |
|  支持: 表单需要滚动的情况                              |
+======================================================+
    """)

    result = {
        'popup_window': {},
        'menu_clicks': {},
        'form_fields': {},
        'scroll': {},
        'tab_order': [],
        'focus_method': '',
        'notes': [],
    }

    # ========== 步骤1: 弹窗 ==========
    print("─"*50)
    print("  步骤1: 识别条件单弹窗")
    print("─"*50)
    print("  打开条件单弹窗,鼠标放在弹窗上")
    input("  按Enter > ")
    
    win_info = get_window_at_mouse()
    result['popup_window'] = win_info
    print(f"  ✓ '{win_info['title']}'")

    # ========== 步骤2: 卖出条件单 ==========
    print("\n" + "─"*50)
    print("  步骤2: 鼠标移到[卖出条件单]上")
    print("─"*50)
    input("  按Enter > ")
    x, y = get_mouse_pos()
    result['menu_clicks']['sell_condition'] = {'x': x, 'y': y}
    print(f"  ✓ ({x}, {y})")
    print("\n  请点击展开它")
    input("  展开后按Enter > ")

    # ========== 步骤3: 止盈止损 ==========
    print("\n" + "─"*50)
    print("  步骤3: 鼠标移到[止盈止损]上")
    print("─"*50)
    input("  按Enter > ")
    x, y = get_mouse_pos()
    result['menu_clicks']['tp_sl'] = {'x': x, 'y': y}
    print(f"  ✓ ({x}, {y})")
    print("\n  请点击打开止盈止损表单")
    input("  表单出现后按Enter > ")
    time.sleep(0.5)

    # ========== 步骤4: 可见区域的字段 ==========
    print("\n" + "─"*50)
    print("  步骤4: 记录表单字段(不滚动,只记录当前能看到的)")
    print("─"*50)
    print("  逐个把鼠标移到输入框中间,按Enter")
    print("  如果某个字段当前看不到,输入 s 跳过")
    print()

    fields = [
        ('code', '证券代码输入框'),
        ('base_price', '基准价输入框'),
        ('tp_price', '止盈条件(>=)输入框'),
        ('sl_price', '止损条件(<=)输入框'),
        ('price_type', '委托价下拉框'),
        ('quantity', '委托数量输入框'),
    ]

    visible_fields = []
    for key, label in fields:
        print(f"  ➜ 【{label}】 (看不到输入s)")
        resp = input(f"    按Enter记录 / 输入s跳过 > ").strip().lower()
        if resp == 's':
            result['form_fields'][key] = {'x': 0, 'y': 0, 'needs_scroll': True}
            print(f"    → 需要滚动才能看到")
        else:
            x, y = get_mouse_pos()
            result['form_fields'][key] = {'x': x, 'y': y, 'needs_scroll': False}
            visible_fields.append(key)
            print(f"    ✓ ({x}, {y})")

    # ========== 步骤5: 滚动区域 ==========
    print("\n" + "─"*50)
    print("  步骤5: 滚动设置")
    print("─"*50)
    print()
    print("  表单需要向下滚动才能看到提交按钮")
    print("  我需要知道在哪里滚动(鼠标滚轮位置)")
    print()
    print("  把鼠标放在表单内容区域(可以滚动的地方)")
    input("  按Enter > ")
    
    x, y = get_mouse_pos()
    result['scroll'] = {'x': x, 'y': y, 'direction': 'down'}
    print(f"  ✓ 滚动区域: ({x}, {y})")
    
    print("\n  现在请手动滚动到能看到[提交条件单]按钮")
    input("  能看到提交按钮后按Enter > ")

    # 记录滚动后才能看到的字段
    print("\n  滚动后,还有需要记录的字段吗?")
    for key, label in fields:
        if result['form_fields'].get(key, {}).get('needs_scroll'):
            print(f"\n  ➜ 【{label}】现在能看到了吗? 鼠标移上去")
            resp = input(f"    按Enter记录 / 输入s仍看不到 > ").strip().lower()
            if resp != 's':
                x, y = get_mouse_pos()
                result['form_fields'][key] = {'x': x, 'y': y, 'needs_scroll': True}
                print(f"    ✓ ({x}, {y}) (需滚动后可见)")

    # 提交按钮
    print("\n  ➜ 鼠标移到【提交条件单】按钮上")
    input("    按Enter > ")
    x, y = get_mouse_pos()
    result['form_fields']['submit_btn'] = {'x': x, 'y': y, 'needs_scroll': True}
    print(f"  ✓ 提交按钮: ({x}, {y}) (滚动后可见)")

    # ========== 步骤6: Tab测试 ==========
    print("\n" + "─"*50)
    print("  步骤6: 测试Tab")
    print("─"*50)
    print()
    print("  请滚动回顶部,确保能看到证券代码输入框")
    input("  准备好按Enter,脚本会自动点击代码框再按Tab > ")
    
    # 用鼠标点击之前记录的证券代码坐标,恢复焦点
    code_pos = result['form_fields'].get('code', {})
    if code_pos.get('x'):
        import ctypes.wintypes
        # 物理点击代码输入框
        windll.user32.SetCursorPos(code_pos['x'], code_pos['y'])
        time.sleep(0.1)
        # 模拟鼠标左键按下+释放
        windll.user32.mouse_event(0x0002, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
        time.sleep(0.05)
        windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP
        time.sleep(0.8)
        print("  → 已自动点击证券代码框")
    
    # 按Tab
    time.sleep(0.3)
    VK_TAB = 0x09
    windll.user32.keybd_event(VK_TAB, 0, 0, 0)
    time.sleep(0.05)
    windll.user32.keybd_event(VK_TAB, 0, 2, 0)
    time.sleep(0.8)
    print("  → 已按Tab")
    print()
    print("  请看弹窗: 焦点是否从证券代码跳到了下一个字段?")
    
    tab_works = input("  跳了吗? (y/n): ").strip().lower()
    
    if tab_works == 'y':
        result['focus_method'] = 'tab'
        print()
        print("  Tab可用! 逐个记录:")
        print("  输入: base_price/tp/sl/price_type/quantity/expire/submit/unknown/q结束")
        
        tab_order = ['code']
        current = input("  Tab跳到了: ").strip()
        if current:
            tab_order.append(current)
        
        print("  (每次输入后我会自动点回弹窗再按Tab)")
        print()
        for i in range(12):
            # 点击弹窗内容区域恢复焦点(用滚动区域坐标,在表单内部)
            scroll_pos = result['scroll']
            windll.user32.SetCursorPos(scroll_pos['x'], scroll_pos['y'])
            time.sleep(0.1)
            windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(0.05)
            windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
            time.sleep(0.3)
            # 按Tab
            windll.user32.keybd_event(VK_TAB, 0, 0, 0)
            time.sleep(0.05)
            windll.user32.keybd_event(VK_TAB, 0, 2, 0)
            time.sleep(0.5)
            field = input("  Tab -> ").strip()
            if not field or field == 'q':
                break
            tab_order.append(field)
        
        result['tab_order'] = tab_order
        print(f"\n  ✓ {' -> '.join(tab_order)}")
    else:
        result['focus_method'] = 'click_coordinates'
        print("  Tab不可用,使用坐标点击")

    # ========== 步骤7: 补充问题 ==========
    print("\n" + "─"*50)
    print("  步骤7: 快速问答")
    print("─"*50)
    
    q1 = input("  输入代码后要从下拉列表选吗? (y/n): ").strip().lower()
    result['notes'].append(f"代码下拉: {'要' if q1=='y' else '不要'}")
    
    q2 = input("  提交后有确认弹窗吗? (y/n/不知道): ").strip()
    result['notes'].append(f"确认弹窗: {q2}")
    
    q3 = input("  默认委托价是? (如 即时买三价): ").strip()
    result['notes'].append(f"默认委托价: {q3}")
    
    q4 = input("  弹窗位置每次固定吗? (y/n): ").strip().lower()
    result['notes'].append(f"位置固定: {'是' if q4=='y' else '否'}")
    
    q5 = input("  滚动大约几下鼠标滚轮能看到提交按钮? (如 3): ").strip()
    result['scroll']['wheel_clicks'] = int(q5) if q5.isdigit() else 3
    result['notes'].append(f"滚动次数: {q5}")

    # ========== 保存 ==========
    print("\n" + "─"*50)
    output_file = "tp_sl_config.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"""
{'='*50}
  采集完成! 保存到: {output_file}
{'='*50}

  弹窗: '{result['popup_window'].get('title')}'
  菜单: 卖出条件单({result['menu_clicks']['sell_condition']['x']},{result['menu_clicks']['sell_condition']['y']}) 
        止盈止损({result['menu_clicks']['tp_sl']['x']},{result['menu_clicks']['tp_sl']['y']})
  滚动: 在({result['scroll']['x']},{result['scroll']['y']})向下滚{result['scroll'].get('wheel_clicks',3)}下
  方式: {result['focus_method']}
  Tab: {' -> '.join(result['tab_order']) if result['tab_order'] else '不可用'}
  备注: {'; '.join(result['notes'])}

  字段:""")
    for key, pos in result['form_fields'].items():
        scroll_mark = " [需滚动]" if pos.get('needs_scroll') else ""
        print(f"    {key:12s} ({pos['x']}, {pos['y']}){scroll_mark}")
    
    print(f"\n  请把 {output_file} 发给我!")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()

