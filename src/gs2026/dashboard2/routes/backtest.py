"""
回溯分析路由 - 买点历史记录和效果追踪
"""
from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, jsonify, request
from sqlalchemy import text
import json

from gs2026.dashboard.services.data_service import DataService
from gs2026.dashboard2.routes.monitor import _get_shared_engine

backtest_bp = Blueprint('backtest', __name__)
data_service = DataService()


def get_engine():
    """获取数据库引擎"""
    return _get_shared_engine()


@backtest_bp.route('/analysis/backtest')
def backtest_page():
    """渲染回溯分析页面"""
    return render_template('backtest.html')


@backtest_bp.route('/api/backtest/records', methods=['POST'])
def query_records():
    """查询买点记录"""
    try:
        data = request.get_json() or {}
        
        start_date = data.get('start_date', (date.today() - timedelta(days=7)).isoformat())
        end_date = data.get('end_date', date.today().isoformat())
        stock_code = data.get('stock_code', '')
        bond_code = data.get('bond_code', '')
        levels = data.get('levels', [1, 2, 3])
        page = data.get('page', 1)
        page_size = data.get('page_size', 50)
        
        offset = (page - 1) * page_size
        
        engine = get_engine()
        
        with engine.connect() as conn:
            # 构建查询条件
            where_clauses = ['date BETWEEN :start_date AND :end_date']
            params = {'start_date': start_date, 'end_date': end_date}
            
            if stock_code:
                where_clauses.append('stock_code = :stock_code')
                params['stock_code'] = stock_code
            
            if bond_code:
                where_clauses.append('bond_code = :bond_code')
                params['bond_code'] = bond_code
            
            if levels and len(levels) > 0:
                where_clauses.append('level IN :levels')
                params['levels'] = tuple(levels)
            else:
                # 如果没有选择任何星级，默认查询所有
                where_clauses.append('level IN (1, 2, 3)')
            
            where_sql = ' AND '.join(where_clauses)
            
            # 查询总数
            count_sql = f"SELECT COUNT(*) as total FROM buy_point_candidates WHERE {where_sql}"
            result = conn.execute(text(count_sql), params)
            total = result.fetchone()[0]
            
            # 查询数据
            params['limit'] = page_size
            params['offset'] = offset
            
            query_sql = f"""
                SELECT * FROM buy_point_candidates 
                WHERE {where_sql}
                ORDER BY date DESC, time DESC
                LIMIT :limit OFFSET :offset
            """
            result = conn.execute(text(query_sql), params)
            
            columns = result.keys()
            rows = []
            for row in result.fetchall():
                row_dict = dict(zip(columns, row))
                # 转换日期格式为字符串
                if row_dict.get('date'):
                    row_dict['date'] = str(row_dict['date'])
                if row_dict.get('time'):
                    # time是timedelta类型，转换为字符串
                    if hasattr(row_dict['time'], 'seconds'):
                        total_seconds = int(row_dict['time'].total_seconds())
                        hours = total_seconds // 3600
                        minutes = (total_seconds % 3600) // 60
                        seconds = total_seconds % 60
                        row_dict['time'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    else:
                        row_dict['time'] = str(row_dict['time'])
                # 转换Decimal为float
                for key in ['stock_price', 'stock_change_pct', 'bond_price', 'bond_change_pct',
                           'result_5m_change', 'result_15m_change', 'result_30m_change', 'result_close_change']:
                    if row_dict.get(key) is not None:
                        row_dict[key] = float(row_dict[key])
                rows.append(row_dict)
            
            # 处理JSON字段
            for row in rows:
                if row.get('conditions'):
                    try:
                        row['conditions'] = json.loads(row['conditions'])
                    except:
                        pass
                if row.get('market_context'):
                    try:
                        row['market_context'] = json.loads(row['market_context'])
                    except:
                        pass
            
            return jsonify({
                'success': True,
                'total': int(total),
                'pages': (int(total) + page_size - 1) // page_size,
                'current_page': page,
                'data': rows
            })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@backtest_bp.route('/api/backtest/stats', methods=['POST'])
def get_stats():
    """获取统计概览"""
    try:
        data = request.get_json() or {}
        start_date = data.get('start_date', (date.today() - timedelta(days=7)).isoformat())
        end_date = data.get('end_date', date.today().isoformat())
        
        engine = get_engine()
        
        with engine.connect() as conn:
            sql = """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN level = 3 THEN 1 ELSE 0 END) as level_3,
                    SUM(CASE WHEN level = 2 THEN 1 ELSE 0 END) as level_2,
                    SUM(CASE WHEN level = 1 THEN 1 ELSE 0 END) as level_1,
                    AVG(CASE WHEN is_success_close THEN 1 ELSE 0 END) as success_rate
                FROM buy_point_candidates
                WHERE date BETWEEN :start_date AND :end_date
            """
            result = conn.execute(text(sql), {
                'start_date': start_date,
                'end_date': end_date
            })
            row = result.fetchone()
            
            return jsonify({
                'success': True,
                'stats': {
                    'total_count': row[0] or 0,
                    'level_3_count': row[1] or 0,
                    'level_2_count': row[2] or 0,
                    'level_1_count': row[3] or 0,
                    'success_rate': round(float(row[4]) * 100, 1) if row[4] else 0
                }
            })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@backtest_bp.route('/api/backtest/tracking', methods=['POST'])
def query_tracking():
    """查询效果追踪"""
    try:
        data = request.get_json() or {}
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        engine = get_engine()
        
        with engine.connect() as conn:
            sql = """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN is_success_5m THEN 1 ELSE 0 END) as success_5m,
                    SUM(CASE WHEN is_success_15m THEN 1 ELSE 0 END) as success_15m,
                    SUM(CASE WHEN is_success_30m THEN 1 ELSE 0 END) as success_30m,
                    SUM(CASE WHEN is_success_close THEN 1 ELSE 0 END) as success_close,
                    AVG(result_5m_change) as avg_change_5m,
                    AVG(result_15m_change) as avg_change_15m,
                    AVG(result_30m_change) as avg_change_30m,
                    AVG(result_close_change) as avg_change_close
                FROM buy_point_candidates
                WHERE date BETWEEN :start_date AND :end_date
                AND result_5m_price IS NOT NULL
            """
            result = conn.execute(text(sql), {
                'start_date': start_date,
                'end_date': end_date
            })
            row = result.fetchone()
            
            total = row[0] or 0
            
            return jsonify({
                'success': True,
                'tracking': {
                    '5m': {
                        'total': total,
                        'success': row[1] or 0,
                        'rate': round(row[1] / total * 100, 1) if total else 0,
                        'avg_change': round(row[5] or 0, 2)
                    },
                    '15m': {
                        'total': total,
                        'success': row[2] or 0,
                        'rate': round(row[2] / total * 100, 1) if total else 0,
                        'avg_change': round(row[6] or 0, 2)
                    },
                    '30m': {
                        'total': total,
                        'success': row[3] or 0,
                        'rate': round(row[3] / total * 100, 1) if total else 0,
                        'avg_change': round(row[7] or 0, 2)
                    },
                    'close': {
                        'total': total,
                        'success': row[4] or 0,
                        'rate': round(row[4] / total * 100, 1) if total else 0,
                        'avg_change': round(row[8] or 0, 2)
                    }
                }
            })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@backtest_bp.route('/api/backtest/detail/<int:id>')
def get_detail(id):
    """获取单个买点详情"""
    try:
        engine = get_engine()
        
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT * FROM buy_point_candidates WHERE id = :id"),
                {'id': id}
            )
            row = result.fetchone()
            
            if not row:
                return jsonify({'success': False, 'error': '记录不存在'})
            
            columns = result.keys()
            data = {}
            for i, col in enumerate(columns):
                data[col] = row[i]
            
            # 转换日期格式
            if data.get('date'):
                data['date'] = str(data['date'])
            if data.get('time'):
                # time是timedelta类型
                if hasattr(data['time'], 'total_seconds'):
                    total_seconds = int(data['time'].total_seconds())
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    seconds = total_seconds % 60
                    data['time'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                else:
                    data['time'] = str(data['time'])
            
            # 转换Decimal为float
            for key in ['stock_price', 'stock_change_pct', 'bond_price', 'bond_change_pct',
                       'result_5m_change', 'result_15m_change', 'result_30m_change', 'result_close_change']:
                if data.get(key) is not None:
                    data[key] = float(data[key])
            
            # 处理JSON字段
            if data.get('conditions'):
                try:
                    data['conditions'] = json.loads(data['conditions'])
                except:
                    pass
            if data.get('market_context'):
                try:
                    data['market_context'] = json.loads(data['market_context'])
                except:
                    pass
            
            return jsonify({'success': True, 'data': data})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
