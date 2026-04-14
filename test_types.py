#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard2.services.ztb_analysis_service import get_ztb_list

result = get_ztb_list(date='20260413', page=1, page_size=1)
items = result.get('items', [])
if items:
    item = items[0]
    print(f"stock_name: {item.get('stock_name')}")
    print(f"sectors type: {type(item.get('sectors'))}")
    print(f"sectors: {item.get('sectors')}")
    print(f"concepts type: {type(item.get('concepts'))}")
    print(f"concepts: {item.get('concepts')}")
