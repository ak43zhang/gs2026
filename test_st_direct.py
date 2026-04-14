import sys
sys.path.insert(0, 'src')

from gs2026.dashboard2.services import ztb_analysis_service

result = ztb_analysis_service.get_ztb_list(date='20260414', market_filter='st', page=1, page_size=20)
print(f"Total: {result.get('total')}")
print(f"Items count: {len(result.get('items', []))}")
