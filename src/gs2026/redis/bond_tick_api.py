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
from typing import List, Dict, Optional
import pandas as pd
import threading

from gs2026.redis.bond_tick_cache import (
    BondTickCache, 
    get_bond_ticks,
    is_cache_enabled
)
from gs2026.utils.mysql_util import get_mysql_tool

# 创建蓝图
bp = Blueprint('bond_tick', __name__, url_prefix='/api/bond/tick')


def _query_mysql(bond_code: str, date: str) -> List[Dict]:
    """
    从MySQL查询债券分时数据
    
    Args:
        bond_code: 债券代码
        date: 日期 (YYYYMMDD)
    
    Returns:
        按时间排序的tick列表
    """
    try:
        table_name = f"monitor_zq_sssj_{date}"
        
        sql = f"""
            SELECT 
                `time`, 
                `price`, 
                `change_pct`, 
                `amount`, 
                `volume`,
                `high`, 
                `low`, 
                `open`, 
                `pre_close`
            FROM `{table_name}`
            WHERE `bond_code` = %s
            ORDER BY `time`
        """
        
        engine = get_mysql_tool().engine
        df = pd.read_sql(sql, engine, params=(bond_code,))
        
        if df.empty:
            return []
        
        # DataFrame转字典列表
        ticks = df.to_dict('records')
        
        # 确保time字段是字符串
        for tick in ticks:
            if hasattr(tick['time'], 'total_seconds'):
                # 处理Timedelta类型
                total_secs = int(tick['time'].total_seconds())
                tick['time'] = f"{total_secs // 3600:02d}:{(total_secs % 3600) // 60:02d}:{total_secs % 60:02d}"
            else:
                tick['time'] = str(tick['time'])
        
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
    """
    获取缓存状态
    
    Response:
        {
            "success": true,
            "cache_enabled": true,
            "status": "up",
            "total_bonds_cached": 320,
            ...
        }
    """
    try:
        cache = BondTickCache.get_instance()
        stats = cache.get_stats()
        
        return jsonify({
            'success': True,
            'cache_enabled': is_cache_enabled(),
            **stats
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
