"""
删除第二个 _enrich_bond_data 函数定义（行2835-2980）
"""

with open('src/gs2026/dashboard2/routes/monitor.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到第二个 _enrich_bond_data 定义的开始和结束
# 第一个定义在行1092（索引1091）
# 第二个定义在行2835（索引2834）

start_line = 2834  # 0-indexed

# 找到 _mark_and_sort_realtime_attacks 的开始（第二个函数之后）
end_line = None
for i in range(start_line, len(lines)):
    if lines[i].strip().startswith('def _mark_and_sort_realtime_attacks'):
        end_line = i
        break

if end_line is None:
    print("找不到 _mark_and_sort_realtime_attacks")
    exit(1)

print(f"删除行 {start_line+1} 到 {end_line}（共 {end_line - start_line} 行）")

# 删除这些行
new_lines = lines[:start_line] + lines[end_line:]

with open('src/gs2026/dashboard2/routes/monitor.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"删除完成，文件现在有 {len(new_lines)} 行")
