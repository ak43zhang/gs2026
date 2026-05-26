import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到第二个 _get_bond_change_pct_batch 函数的位置
start_line = None
end_line = None

for i, l in enumerate(lines):
    if 'def _get_bond_change_pct_batch' in l:
        if start_line is None:
            start_line = i  # 第一个
        else:
            start_line = i  # 第二个
            break

if start_line is None:
    print("ERROR: Could not find second function")
    sys.exit(1)

# 找到第二个函数的结束位置（下一个函数定义或类定义）
for i in range(start_line + 1, len(lines)):
    if lines[i].strip().startswith('def ') or lines[i].strip().startswith('class '):
        end_line = i
        break

if end_line is None:
    end_line = len(lines)

print(f"Second function at lines {start_line+1} to {end_line}")

# 删除第二个函数（包括前面的空行）
new_lines = lines[:start_line] + lines[end_line:]

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"Deleted lines {start_line+1} to {end_line}")
print("OK: Second function removed")
