import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py', 'r', encoding='utf-8') as f:
    c = f.read()

# 检查是否有 price 处理逻辑
if 'price_map = df.set_index(code_col)' in c:
    print("Price logic found in file")
else:
    print("Price logic NOT found in file")

# 检查是否有 .str.replace
if ".str.replace('.0', '', regex=False)" in c:
    print("Found .str.replace('.0'...) - this is old code")
else:
    print("No .str.replace found - this should be new code")
