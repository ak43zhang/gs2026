#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard2.services.ztb_analysis_service import get_ztb_detail

result = get_ztb_detail('82a8fa78cfea9bfd64fa3143e41a18cd', '20260413')

if result.get('code') == 0:
    data = result['data']
    print("板块消息 (sector_msg):")
    print(json.dumps(data.get('sector_msg', []), ensure_ascii=False, indent=2))
    print("\n概念消息 (concept_msg):")
    print(json.dumps(data.get('concept_msg', []), ensure_ascii=False, indent=2))
    print("\n龙头股消息 (leading_stock_msg):")
    print(json.dumps(data.get('leading_stock_msg', []), ensure_ascii=False, indent=2))
    print("\n影响消息 (influence_msg):")
    print(json.dumps(data.get('influence_msg', []), ensure_ascii=False, indent=2))
    print("\n预期消息 (expect_msg):")
    print(json.dumps(data.get('expect_msg', []), ensure_ascii=False, indent=2))
else:
    print(f"Error: {result}")
