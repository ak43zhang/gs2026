import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

import adata

df = adata.bond.market.list_market_current()
print(f"Columns: {list(df.columns)}")
print(df.head(3))
