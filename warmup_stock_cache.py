#!/usr/bin/env python3
"""预热宽表缓存"""
import sys
sys.path.insert(0, 'src')

from gs2026.dashboard2.services import stock_picker_service

print("Starting warm up...")
stock_picker_service.warm_up_cache()
print("Warm up completed!")
