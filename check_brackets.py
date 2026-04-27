#!/usr/bin/env python3
"""检查JavaScript括号匹配"""
import re

def check_brackets(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取所有script内容
    scripts = re.findall(r'<script>(.*?)</script>', content, re.DOTALL)
    
    print("=" * 60)
    print("JavaScript括号匹配检查")
    print("=" * 60)
    
    for i, script in enumerate(scripts):
        print(f"\nScript {i+1}:")
        
        # 计算括号
        open_braces = script.count('{')
        close_braces = script.count('}')
        open_parens = script.count('(')
        close_parens = script.count(')')
        open_brackets = script.count('[')
        close_brackets = script.count(']')
        
        print(f"  花括号: {{ {open_braces} vs }} {close_braces} - {'OK' if open_braces == close_braces else 'MISMATCH'}")
        print(f"  圆括号: ( {open_parens} vs ) {close_parens} - {'OK' if open_parens == close_parens else 'MISMATCH'}")
        print(f"  方括号: [ {open_brackets} vs ] {close_brackets} - {'OK' if open_brackets == close_brackets else 'MISMATCH'}")
        
        # 检查特定语法
        if 'Promise.all(' in script:
            # 检查Promise.all的括号
            promise_matches = re.findall(r'Promise\.all\((.*?)\)', script, re.DOTALL)
            print(f"  Promise.all调用: {len(promise_matches)} 处")
        
        if 'const [' in script or 'let [' in script:
            # 检查解构赋值
            destruct_matches = re.findall(r'(?:const|let)\s+\[([^\]]+)\]', script)
            print(f"  数组解构赋值: {len(destruct_matches)} 处")
        
        # 检查async/await
        async_funcs = re.findall(r'async\s+function', script)
        print(f"  async函数: {len(async_funcs)} 个")
        
        # 检查箭头函数
        arrow_funcs = re.findall(r'\)\s*=>', script)
        print(f"  箭头函数: {len(arrow_funcs)} 个")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    check_brackets(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html')
