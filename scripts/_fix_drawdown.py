import re

with open('src/gs2026/dashboard2/services/backtest_bond.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = "'max_loss_pct': 0, 'total_return_pct': 0, 'avg_duration_sec': 0"
new = "'max_loss_pct': 0, 'total_return_pct': 0, 'max_drawdown_pct': 0, 'avg_duration_sec': 0"

count = content.count(old)
content = content.replace(old, new)

with open('src/gs2026/dashboard2/services/backtest_bond.py', 'w', encoding='utf-8') as f:
    f.write(content)

print(f"Replaced {count} instances")
