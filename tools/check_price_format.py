"""
检查后端返回的价格数据格式
"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard.services.data_service import DataService

data_service = DataService()

# 获取股票排行数据
data = data_service.get_rising_ranking(asset_type='stock', limit=10, date='20260519', use_mysql=True)

print("股票排行前3条:")
for item in data[:3]:
    code = item.get('stock_code', 'N/A')
    price = item.get('price', 'N/A')
    price_type = type(price).__name__
    print(f"  {code}: price={price} (type={price_type})")
