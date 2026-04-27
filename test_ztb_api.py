#!/usr/bin/env python3
"""直接测试get_ztb_tags API"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026')

from gs2026.dashboard2.services.stock_picker_service import get_ztb_tags
from loguru import logger

def test_ztb_tags():
    logger.info("=" * 60)
    logger.info("测试get_ztb_tags API")
    logger.info("=" * 60)
    
    # 测试4月27日
    logger.info("\n【测试4月27日】")
    result = get_ztb_tags('20260427')
    logger.info(f"日期: {result['date']}")
    logger.info(f"涨停总数: {result['total_zt']}")
    logger.info(f"行业数量: {len(result['industries'])}")
    logger.info(f"概念数量: {len(result['concepts'])}")
    
    if result['industries']:
        logger.info(f"前3行业: {result['industries'][:3]}")
    
    # 测试4月28日
    logger.info("\n【测试4月28日】")
    result = get_ztb_tags('20260428')
    logger.info(f"日期: {result['date']}")
    logger.info(f"涨停总数: {result['total_zt']}")

if __name__ == "__main__":
    test_ztb_tags()
