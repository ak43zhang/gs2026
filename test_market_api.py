"""测试大盘数据API"""
from gs2026.dashboard.services.data_service import DataService
import json

ds = DataService()

# 测试获取大盘数据
print('Testing get_market_stats with MySQL...')
result = ds.get_market_stats(date='20260401', use_mysql=True)
print(f'Stock data: {result.get("stock")}')
print(f'Bond data: {result.get("bond")}')
