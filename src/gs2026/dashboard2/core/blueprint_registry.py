"""
蓝图注册器 - 统一管理所有蓝图
- 自动发现
- 统一注册
- 错误处理
- 依赖检查
"""

import logging
from typing import Tuple

logger = logging.getLogger('dashboard2.registry')

class BlueprintRegistry:
    """蓝图注册器"""
    
    # 蓝图配置表（模块路径, 蓝图变量名, URL前缀, 是否必需）
    BLUEPRINTS = [
        ('gs2026.dashboard2.routes.auth', 'auth_bp', None, True),
        ('gs2026.dashboard2.routes.collection', 'collection_bp', None, False),
        ('gs2026.dashboard2.routes.analysis', 'analysis_bp', None, False),
        ('gs2026.dashboard2.routes.monitor', 'monitor_bp', '/api/monitor', True),
        ('gs2026.dashboard2.routes.backtest', 'backtest_bp', None, False),
        ('gs2026.dashboard2.routes.stock_bond_mapping', 'bp', None, False),
        ('gs2026.dashboard2.routes.red_list', 'bp', None, False),
        ('gs2026.dashboard2.routes.green_bond_list', 'bp', None, False),
        ('gs2026.dashboard2.routes.news', 'news_bp', None, False),
        ('gs2026.dashboard2.routes.domain_analysis', 'domain_bp', None, False),
        ('gs2026.dashboard2.routes.ztb_analysis', 'ztb_bp', None, False),
        ('gs2026.dashboard2.routes.notice_analysis', 'notice_bp', None, False),
        ('gs2026.dashboard2.routes.analysis_center', 'analysis_center_bp', None, False),
        ('gs2026.dashboard2.routes.notice_page', 'notice_analysis_bp', None, False),
        ('gs2026.dashboard2.routes.domain_page', 'domain_analysis_bp', None, False),
        ('gs2026.dashboard2.routes.scheduler', 'scheduler_bp', None, False),
        ('gs2026.dashboard2.routes.performance', 'performance_bp', None, False),
        ('gs2026.dashboard2.routes.report', 'report_bp', None, False),
        ('gs2026.dashboard2.routes.stock_picker', 'stock_picker_bp', None, False),
        ('gs2026.dashboard2.routes.profile', 'profile_bp', None, False),
        ('gs2026.dashboard2.routes.challenges', 'challenge_bp', None, False),
        ('gs2026.dashboard2.routes.trading_rules', 'rules_bp', None, False),
    ]
    
    @classmethod
    def register_all(cls, app) -> Tuple[int, int]:
        """
        注册所有蓝图
        
        Returns:
            (成功数, 失败数)
        """
        success_count = 0
        fail_count = 0
        
        for module_path, bp_name, url_prefix, required in cls.BLUEPRINTS:
            try:
                # 动态导入
                module = __import__(module_path, fromlist=[bp_name])
                blueprint = getattr(module, bp_name)
                
                # 注册
                if url_prefix:
                    app.register_blueprint(blueprint, url_prefix=url_prefix)
                else:
                    app.register_blueprint(blueprint)
                
                logger.info(f"✓ {bp_name} 已注册")
                success_count += 1
                
            except Exception as e:
                fail_count += 1
                if required:
                    logger.error(f"✗ {bp_name} 注册失败（必需模块）: {e}")
                    raise  # 必需模块失败则中断启动
                else:
                    logger.warning(f"⚠ {bp_name} 注册失败（可选模块）: {e}")
        
        return success_count, fail_count
