"""
可转债分时图API - 可插拔版本

提供REST API接口:
- GET /api/bond/tick/<bond_code>  获取单债券全天数据
- GET /api/bond/tick/status       获取缓存状态

特性:
- 优先Redis，降级MySQL
- 异步回填
- 可插拔开关
"""

from flask import Blueprint, jsonify, request, current_app
from datetime import datetime
from typing import List, Dict
import threading

from gs2026.redis.bond_tick_cache import (
    BondTickCache, 
    get_bond_ticks,
    is_cache_enabled
)

# 创建蓝图（url_prefix由blueprint_registry统一管理）
bp = Blueprint('bond_tick', __name__)


def _query_mysql(bond_code: str, date: str) -> List[Dict]:
    """
    从MySQL查询债券分时数据（使用已有引擎，不创建新连接）
    """
    try:
        from gs2026.utils.config_util import get_engine
        from sqlalchemy import text
        
        table_name = f"monitor_zq_sssj_{date}"
        engine = get_engine()
        
        sql = text(f"""
            SELECT `time`, `price`, `change_pct`, `amount`, `volume`,
                   `high`, `low`, `open`, `pre_close`
            FROM `{table_name}`
            WHERE `bond_code` = :code
            ORDER BY `time`
        """)
        
        with engine.connect() as conn:
            result = conn.execute(sql, {'code': bond_code})
            rows = result.fetchall()
        
        if not rows:
            return []
        
        columns = ['time', 'price', 'change_pct', 'amount', 'volume',
                   'high', 'low', 'open', 'pre_close']
        ticks = []
        for row in rows:
            tick = dict(zip(columns, row))
            # 处理time字段
            t = tick['time']
            if hasattr(t, 'total_seconds'):
                total_secs = int(t.total_seconds())
                tick['time'] = f"{total_secs // 3600:02d}:{(total_secs % 3600) // 60:02d}:{total_secs % 60:02d}"
            else:
                tick['time'] = str(t)
            # 数值转换
            for k in ['price', 'change_pct', 'amount', 'volume', 'high', 'low', 'open', 'pre_close']:
                if tick[k] is not None:
                    tick[k] = float(tick[k])
            ticks.append(tick)
        
        return ticks
        
    except Exception as e:
        current_app.logger.error(f"[BondTickAPI] MySQL查询失败 {bond_code}: {e}")
        return []


def _backfill_to_redis(bond_code: str, date: str, ticks: List[Dict]):
    """
    异步回填数据到Redis
    
    在后台线程执行，不阻塞API响应
    """
    def do_backfill():
        try:
            cache = BondTickCache.get_instance()
            if not cache.is_enabled():
                return
            
            success = cache.write_batch(bond_code, ticks)
            if success:
                current_app.logger.info(
                    f"[BondTickAPI] 回填成功 {bond_code}: {len(ticks)}条"
                )
        except Exception as e:
            current_app.logger.warning(f"[BondTickAPI] 回填失败 {bond_code}: {e}")
    
    # 启动后台线程
    thread = threading.Thread(
        target=do_backfill,
        daemon=True,
        name=f"Backfill-{bond_code}"
    )
    thread.start()


# ==================== API路由 ====================

@bp.route('/<bond_code>')
def get_ticks(bond_code: str):
    """
    获取单债券全天分时数据
    
    Query参数:
        date: 日期 (YYYYMMDD)，默认今天
    
    Response:
        {
            "success": true,
            "bond_code": "110072",
            "date": "20260720",
            "source": "redis" | "mysql",
            "count": 4800,
            "data": [
                {
                    "time": "09:30:03",
                    "price": 115.50,
                    "change_pct": 2.35,
                    ...
                },
                ...
            ]
        }
    """
    # 参数解析
    date = request.args.get('date', datetime.now().strftime('%Y%m%d'))
    
    # 输入验证
    if not bond_code or len(bond_code) < 6:
        return jsonify({
            'success': False,
            'message': '债券代码无效'
        }), 400
    
    try:
        # 1. 尝试从Redis获取
        ticks = []
        source = 'redis'
        
        if is_cache_enabled():
            ticks = get_bond_ticks(bond_code, date)
        
        # 2. Redis无数据或缓存禁用，从MySQL查询
        if not ticks:
            source = 'mysql'
            ticks = _query_mysql(bond_code, date)
            
            # 异步回填Redis（如果启用）
            if ticks and is_cache_enabled():
                _backfill_to_redis(bond_code, date, ticks)
        
        # 3. 返回结果
        if not ticks:
            return jsonify({
                'success': False,
                'bond_code': bond_code,
                'date': date,
                'message': '无数据'
            }), 404
        
        return jsonify({
            'success': True,
            'bond_code': bond_code,
            'date': date,
            'source': source,
            'count': len(ticks),
            'cache_enabled': is_cache_enabled(),
            'data': ticks
        })
        
    except Exception as e:
        current_app.logger.error(f"[BondTickAPI] 异常: {e}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}'
        }), 500


@bp.route('/status')
def get_status():
    """诊断端点 - 查看Redis缓存状态"""
    try:
        # 1. 检查配置
        from gs2026.redis.bond_tick_cache import CacheConfig
        
        # 2. 检查全局Redis客户端
        from gs2026.utils.redis_util import _get_redis_client, _redis_client
        global_client = _get_redis_client()
        
        # 3. 检查BondTickCache._redis()
        cache_redis = BondTickCache._redis()
        
        # 4. 尝试ping
        ping_ok = False
        try:
            if cache_redis:
                ping_ok = cache_redis.ping()
        except Exception as e:
            ping_ok = f"ERROR: {e}"
        
        # 5. 尝试读取测试数据
        test_count = 0
        try:
            if cache_redis:
                test_count = cache_redis.hlen('bond:tick:111060:20260717')
        except Exception:
            pass
        
        return jsonify({
            'success': True,
            'diagnostic': {
                'CacheConfig.ENABLED': CacheConfig.ENABLED,
                'is_cache_enabled()': is_cache_enabled(),
                'global_redis_client': str(global_client),
                'global_redis_is_none': global_client is None,
                'BondTickCache._redis()': str(cache_redis),
                'cache_redis_is_none': cache_redis is None,
                'ping': ping_ok,
                'test_data_111060': test_count,
                '_fail_count': BondTickCache._fail_count,
                '_disabled_until': BondTickCache._disabled_until,
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@bp.route('/clear', methods=['POST'])
def clear_cache():
    """
    手动清理缓存（管理接口）
    
    Body参数:
        date: 日期 (YYYYMMDD)，默认今天
    
    注意: 此接口需谨慎使用
    """
    # 简单权限检查（可通过IP或token增强）
    # TODO: 增加权限验证
    
    date = request.json.get('date', datetime.now().strftime('%Y%m%d'))
    
    try:
        cache = BondTickCache.get_instance()
        count = cache.clear(date)
        
        return jsonify({
            'success': True,
            'date': date,
            'cleared_bonds': count
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


# ==================== 模块初始化 ====================

def init_app(app):
    """
    初始化API模块
    
    在应用启动时调用:
        init_app(app)
    """
    app.register_blueprint(bp)
    
    # 初始化缓存连接
    BondTickCache.get_instance()
    
    app.logger.info("[BondTickAPI] API模块已注册")
