"""
初始化管理器 - 统一管理启动任务
- Redis连接
- 缓存预热
- 定时任务
- 健康检查
"""

import logging
from typing import Dict, Any

logger = logging.getLogger('dashboard2.initializer')

class Initializer:
    """初始化管理器"""
    
    @staticmethod
    def init_redis(app) -> bool:
        """初始化Redis连接"""
        try:
            from gs2026.utils import redis_util
            if redis_util._redis_client is None:
                redis_util.init_redis()
            logger.info("✓ Redis连接已建立")
            return True
        except Exception as e:
            logger.error(f"✗ Redis初始化失败: {e}")
            return False
    
    @staticmethod
    def init_redis_dicts(app) -> bool:
        """初始化Redis字典数据（MySQL → Redis）"""
        try:
            from gs2026.utils.redis_util import (
                mysql2redis_generate_dict,
                init_stock_industry_mapping_to_redis,
                init_industry_stock_count_to_redis
            )
            with app.app_context():
                mysql2redis_generate_dict("data_industry_code_ths", 'code,name')
                mysql2redis_generate_dict("data_bond_ths", '债券代码 as code,债券简称 as name,正股代码 as stock_code')
                init_stock_industry_mapping_to_redis()
                init_industry_stock_count_to_redis()
            logger.info("✓ Redis字典数据已初始化（行业代码/债券映射/股票行业映射/行业股票数量）")
            return True
        except Exception as e:
            logger.error(f"✗ Redis字典初始化失败: {e}")
            return False

    @staticmethod
    def init_cache(app) -> Dict[str, Any]:
        """初始化缓存（同步+异步）"""
        results = {}
        try:
            from gs2026.dashboard2.cache import init_all_caches, cache_manager
            
            # 注册所有缓存
            init_all_caches()
            
            # 预热需要app context（数据库查询）
            with app.app_context():
                warmup_results = cache_manager.warmup_all(sync_names=['red_list'])
            
            for name, result in warmup_results.items():
                status = "✓" if result.get('success') else "✗"
                logger.info(f"{status} {name}: {result.get('message', '')}")
            
            logger.info("✓ 异步缓存预热已启动")
            results['warmup'] = warmup_results
            
        except Exception as e:
            logger.error(f"✗ 缓存初始化失败: {e}")
            results['error'] = str(e)
        
        return results
    
    @staticmethod
    def init_scheduler(app) -> bool:
        """初始化智能选股缓存"""
        try:
            from gs2026.dashboard2.services import stock_picker_service
            with app.app_context():
                stock_picker_service.init_service()
            logger.info("✓ 智能选股缓存已初始化")
            return True
        except Exception as e:
            logger.warning(f"⚠ 智能选股缓存初始化失败: {e}")
            return False
    
    @classmethod
    def run_all(cls, app) -> Dict[str, Any]:
        """
        执行所有初始化任务
        
        Returns:
            初始化结果摘要
        """
        logger.info("=" * 60)
        logger.info("开始初始化...")
        logger.info("=" * 60)
        
        results = {
            'redis': cls.init_redis(app),
            'redis_dicts': cls.init_redis_dicts(app),
            'cache': cls.init_cache(app),
            'scheduler': cls.init_scheduler(app),
        }
        
        logger.info("=" * 60)
        logger.info(f"初始化完成: Redis={results['redis']}, Dicts={results['redis_dicts']}, Scheduler={results['scheduler']}")
        logger.info("=" * 60)
        
        return results
