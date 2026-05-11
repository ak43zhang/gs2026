# -*- coding: utf-8 -*-
"""测试公告原文抓取工具 — 取100条验证"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.collection.risk.notice_content_fetcher import fetch_batch_content

# 测试：抓取2026-04-30的公告，限制100条
fetch_batch_content('jhsaggg2026', '2026-04-30', limit=100)
