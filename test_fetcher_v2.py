# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')
from gs2026.collection.risk.notice_content_fetcher import fetch_batch_content

# 测试200条
fetch_batch_content('jhsaggg2026', '2026-04-29', limit=200)
