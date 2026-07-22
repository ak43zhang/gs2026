"""Fix: ensure _adjust_deadline_for_lunch is called in Phase 3"""
import re

filepath = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\services\backtest_bond.py'

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 1. Check if function definition exists
func_exists = any('def _adjust_deadline_for_lunch' in line for line in lines)
print(f"Function definition exists: {func_exists}")

# 2. Find all lines with max_exit_td assignment
for i, line in enumerate(lines, 1):
    if 'max_exit_td' in line and '=' in line and 'Timedelta' in line:
        print(f"Found deadline calc at line {i}: {line.rstrip()}")

# 3. Find all lines calling _adjust_deadline_for_lunch
for i, line in enumerate(lines, 1):
    if '_adjust_deadline_for_lunch' in line and 'def ' not in line:
        print(f"Found call at line {i}: {line.rstrip()}")

# 4. Fix: replace any max_exit_td = ... + Timedelta(minutes=window_minutes) with adjusted version
fixed = False
for i, line in enumerate(lines):
    if 'max_exit_td' in line and 'Timedelta' in line and 'window_minutes' in line and '_adjust_deadline' not in line:
        indent = len(line) - len(line.lstrip())
        spaces = ' ' * indent
        lines[i] = f"{spaces}max_exit_td = _adjust_deadline_for_lunch(entry_td, window_minutes)\n"
        print(f"FIXED line {i+1}: {lines[i].rstrip()}")
        fixed = True

if not fixed:
    # Try alternative pattern: entry_time_td + Timedelta
    for i, line in enumerate(lines):
        if ('entry_td' in line or 'entry_time' in line or 'signal_time' in line) and 'Timedelta' in line and 'window' in line and '_adjust' not in line:
            if 'max_exit' in line or 'deadline' in line or 'timeout' in line:
                indent = len(line) - len(line.lstrip())
                spaces = ' ' * indent
                # Extract variable name
                var_name = line.split('=')[0].strip()
                lines[i] = f"{spaces}{var_name} = _adjust_deadline_for_lunch(entry_td, window_minutes)\n"
                print(f"FIXED (alt) line {i+1}: {lines[i].rstrip()}")
                fixed = True

if fixed:
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print("\nFile updated successfully!")
else:
    print("\nNo matching deadline pattern found. Showing timeout-related lines:")
    for i, line in enumerate(lines, 1):
        if any(kw in line for kw in ['timeout', 'window_minutes', 'max_exit', 'deadline']):
            if 'def ' not in line and '#' not in line.lstrip()[:1]:
                print(f"  {i}: {line.rstrip()}")
