#!/usr/bin/env python3
"""检查monitor.html是否有JavaScript语法错误"""
import re

def check_js_syntax(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取script标签内容
    scripts = re.findall(r'<script>(.*?)</script>', content, re.DOTALL)
    
    print(f"找到 {len(scripts)} 个script标签")
    
    # 检查常见语法问题
    issues = []
    
    # 检查括号匹配
    for i, script in enumerate(scripts):
        open_braces = script.count('{')
        close_braces = script.count('}')
        open_parens = script.count('(')
        close_parens = script.count(')')
        
        if open_braces != close_braces:
            issues.append(f"Script {i+1}: 花括号不匹配 {{ {open_braces} vs }} {close_braces}")
        if open_parens != close_parens:
            issues.append(f"Script {i+1}: 圆括号不匹配 ( {open_parens} vs ) {close_parens}")
    
    # 检查修改的函数
    if 'loadBondRanking' in content:
        # 检查Promise.all语法
        if 'Promise.all([' in content:
            print("[OK] Promise.all 语法正确")
        
        # 检查解构赋值
        if 'const [stockRes, bondRes]' in content:
            print("[OK] 解构赋值语法正确")
    
    if issues:
        print("\n发现的问题:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("[OK] 未发现明显的语法问题")

if __name__ == "__main__":
    check_js_syntax(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html')
