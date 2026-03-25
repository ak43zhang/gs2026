"""
检查 control.html 是否有语法错误
"""

from pathlib import Path
import re

html_path = Path(r"F:\pyworkspace2026\gs2026\src\gs2026\dashboard\templates\control.html")
content = html_path.read_text(encoding='utf-8')

# 检查关键元素
print("检查关键元素...")
check1 = 'id="tab-monitor"' in content
print(f"1. tab-monitor 存在: {check1}")
check2 = 'id="tab-analysis"' in content
print(f"2. tab-analysis 存在: {check2}")
check3 = 'function switchTab' in content
print(f"3. switchTab 函数存在: {check3}")
check4 = '.tab-content' in content
print(f"4. tab-content CSS 存在: {check4}")

# 检查HTML结构
monitor_start = content.find('<div class="tab-content active" id="tab-monitor">')
analysis_start = content.find('<div class="tab-content" id="tab-analysis">')

print(f"\n5. tab-monitor 位置: {monitor_start}")
print(f"6. tab-analysis 位置: {analysis_start}")

# 检查div嵌套
monitor_end = content.find('</div><!-- 关闭 tab-monitor -->', monitor_start)
analysis_end = content.find('</div><!-- 关闭 tab-analysis -->', analysis_start)

print(f"7. tab-monitor 结束位置: {monitor_end}")
print(f"8. tab-analysis 结束位置: {analysis_end}")

# 检查script标签
script_count = content.count('<script>')
print(f"\n9. script 标签数量: {script_count}")

# 检查括号匹配
open_braces = content.count('{')
close_braces = content.count('}')
print(f"\n10. 花括号匹配: 开={open_braces}, 闭={close_braces}")

open_parens = content.count('(')
close_parens = content.count(')')
print(f"11. 圆括号匹配: 开={open_parens}, 闭={close_parens}")

# 检查是否有未闭合的标签
unclosed_divs = content.count('<div') - content.count('</div>')
print(f"\n12. div 标签平衡: {unclosed_divs} (应为0)")

print("\n检查完成!")