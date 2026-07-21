"""Check and fix _PHYSICAL_COLUMNS in backtest_bond.py"""
import os

filepath = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\services\backtest_bond.py'

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

if '_PHYSICAL_COLUMNS' in content:
    print("OK: _PHYSICAL_COLUMNS already exists")
else:
    print("MISSING: Adding _PHYSICAL_COLUMNS...")
    # Insert after "from sqlalchemy import text"
    old = "from sqlalchemy import text"
    new = """from sqlalchemy import text


# 物理列（数据库表中的实际列，可用于SQL WHERE过滤）
_PHYSICAL_COLUMNS = {
    'bond_code', 'bond_name', 'time', 'price', 'change_pct', 'amount',
    'amount_rank', 'min1_change_pct', 'min1_amount', 'min1_amount_rank',
    'slope_short', 'slope_long', 'peak_vol_bias', 'high_distance',
    'mkt_slope_short', 'mkt_slope_long', 'mkt_peak_vol_bias', 'mkt_high_distance'
}"""
    content = content.replace(old, new, 1)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("FIXED: _PHYSICAL_COLUMNS added")

# Verify
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()
print(f"Verify: '_PHYSICAL_COLUMNS' in file = {'_PHYSICAL_COLUMNS' in content}")
print(f"File size: {os.path.getsize(filepath)} bytes")
print(f"Last modified: {os.path.getmtime(filepath)}")
