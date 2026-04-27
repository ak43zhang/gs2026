#!/usr/bin/env python3
"""深度排查monitor.html的日期选择问题"""
import re

def deep_check(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("=" * 60)
    print("深度排查报告")
    print("=" * 60)
    
    # 1. 检查日期选择器HTML
    date_picker_match = re.search(r'<input[^>]*id=["\']date-picker["\'][^>]*>', content)
    if date_picker_match:
        print(f"\n[OK] 找到日期选择器: {date_picker_match.group()}")
    else:
        print("\n[ERROR] 未找到日期选择器!")
    
    # 2. 检查initDatePicker函数
    init_match = re.search(r'\(function initDatePicker\(\)[^{]*\{([^}]*\{[^}]*\}[^}]*)*\}\)\(\);', content, re.DOTALL)
    if init_match:
        print("\n[OK] 找到initDatePicker函数")
        # 检查关键代码
        init_code = init_match.group()
        checks = [
            ('getElementById', '获取元素'),
            ('addEventListener', '绑定事件'),
            ('change', 'change事件'),
            ('loadTimestamps', '调用loadTimestamps'),
            ('loadAllData', '调用loadAllData'),
        ]
        for pattern, desc in checks:
            if pattern in init_code:
                print(f"  [OK] 包含: {desc}")
            else:
                print(f"  [WARN] 缺少: {desc}")
    else:
        print("\n[ERROR] 未找到initDatePicker函数!")
    
    # 3. 检查是否有多个date-picker
    all_pickers = re.findall(r'<input[^>]*id=["\']date-picker["\'][^>]*>', content)
    print(f"\n[INFO] 找到 {len(all_pickers)} 个date-picker元素")
    if len(all_pickers) > 1:
        print("  [WARN] 有多个date-picker，可能导致冲突!")
    
    # 4. 检查script标签完整性
    script_tags = re.findall(r'<script[^>]*>', content)
    print(f"\n[INFO] 找到 {len(script_tags)} 个script开始标签")
    
    close_script_tags = content.count('</script>')
    print(f"[INFO] 找到 {close_script_tags} 个script结束标签")
    
    if len(script_tags) != close_script_tags:
        print("  [ERROR] script标签不匹配!")
    
    # 5. 检查括号匹配（在script内容中）
    scripts = re.findall(r'<script>(.*?)</script>', content, re.DOTALL)
    for i, script in enumerate(scripts):
        open_braces = script.count('{')
        close_braces = script.count('}')
        open_parens = script.count('(')
        close_parens = script.count(')')
        
        issues = []
        if open_braces != close_braces:
            issues.append(f"花括号: {open_braces} vs {close_braces}")
        if open_parens != close_parens:
            issues.append(f"圆括号: {open_parens} vs {close_parens}")
        
        if issues:
            print(f"\n[ERROR] Script {i+1} 括号不匹配:")
            for issue in issues:
                print(f"  - {issue}")
    
    # 6. 检查是否有语法错误的关键字
    print("\n[INFO] 检查关键函数定义:")
    key_functions = [
        'initDatePicker',
        'getSelectedDate',
        'resetToToday',
        'loadAllData',
        'loadTimestamps',
        'toggleLive',
    ]
    for func in key_functions:
        pattern = rf'function\s+{func}\s*\(|async\s+function\s+{func}\s*\('
        if re.search(pattern, content):
            print(f"  [OK] {func}")
        else:
            print(f"  [WARN] 未找到: {func}")
    
    # 7. 检查HTML结构完整性
    print("\n[INFO] 检查HTML结构:")
    html_checks = [
        ('<html', 'html开始'),
        ('</html>', 'html结束'),
        ('<body', 'body开始'),
        ('</body>', 'body结束'),
        ('<head>', 'head开始'),
        ('</head>', 'head结束'),
    ]
    for tag, desc in html_checks:
        if tag in content.lower():
            print(f"  [OK] {desc}")
        else:
            print(f"  [WARN] 缺少: {desc}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    deep_check(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html')
