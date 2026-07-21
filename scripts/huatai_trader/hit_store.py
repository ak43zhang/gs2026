"""
自动交易命中记录 MySQL 持久化模块

表结构: auto_trade_hits
功能: 命中写入、状态更新、查询pending记录
"""
import json
import time
from datetime import datetime, date
from typing import List, Dict, Optional

# 延迟导入，避免循环依赖
_engine = None


def _get_engine():
    """获取数据库引擎(延迟初始化)"""
    global _engine
    if _engine is None:
        try:
            import sys
            sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')
            from gs2026.utils import config_util
            _engine = config_util.get_engine()
        except Exception as e:
            print(f"[hit_store] 数据库连接失败: {e}")
            return None
    return _engine


def init_table():
    """创建命中记录表(如果不存在)"""
    engine = _get_engine()
    if not engine:
        return False
    
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS auto_trade_hits (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    bond_code VARCHAR(10) NOT NULL,
                    bond_name VARCHAR(30) DEFAULT '',
                    hit_price DECIMAL(10,4) DEFAULT 0,
                    scheme_json TEXT,
                    lots INT DEFAULT 1,
                    status ENUM('pending','trading','filled','cancelled','expired','force_sold') DEFAULT 'pending',
                    mode VARCHAR(10) DEFAULT 'full',
                    tp_level DECIMAL(10,4) DEFAULT 0,
                    sl_level DECIMAL(10,4) DEFAULT 0,
                    fill_price DECIMAL(10,4) DEFAULT 0,
                    sell_price DECIMAL(10,4) DEFAULT 0,
                    hit_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    note VARCHAR(200) DEFAULT '',
                    INDEX idx_status (status),
                    INDEX idx_date (hit_time)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """))
            conn.commit()
        return True
    except Exception as e:
        print(f"[hit_store] 建表失败: {e}")
        return False


def save_hit(code: str, name: str, price: float, scheme: dict, lots: int) -> Optional[int]:
    """
    保存命中记录
    
    Returns:
        记录ID，失败返回None
    """
    engine = _get_engine()
    if not engine:
        return None
    
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            result = conn.execute(text("""
                INSERT INTO auto_trade_hits (bond_code, bond_name, hit_price, scheme_json, lots)
                VALUES (:code, :name, :price, :scheme, :lots)
            """), {
                'code': code,
                'name': name,
                'price': price,
                'scheme': json.dumps(scheme, ensure_ascii=False),
                'lots': lots,
            })
            conn.commit()
            return result.lastrowid
    except Exception as e:
        print(f"[hit_store] 保存命中失败: {e}")
        return None


def update_status(hit_id: int, status: str, **kwargs):
    """
    更新命中记录状态
    
    Args:
        hit_id: 记录ID
        status: pending/trading/filled/cancelled/expired/force_sold
        **kwargs: 其他字段(tp_level, sl_level, fill_price, sell_price, note)
    """
    engine = _get_engine()
    if not engine:
        return
    
    try:
        from sqlalchemy import text
        
        set_parts = ["status = :status"]
        params = {'id': hit_id, 'status': status}
        
        for key in ('tp_level', 'sl_level', 'fill_price', 'sell_price', 'note', 'mode'):
            if key in kwargs:
                set_parts.append(f"{key} = :{key}")
                params[key] = kwargs[key]
        
        sql = f"UPDATE auto_trade_hits SET {', '.join(set_parts)} WHERE id = :id"
        
        with engine.connect() as conn:
            conn.execute(text(sql), params)
            conn.commit()
    except Exception as e:
        print(f"[hit_store] 更新状态失败: {e}")


def get_pending_hits() -> List[Dict]:
    """获取所有pending状态的命中(面板启动时加载)"""
    engine = _get_engine()
    if not engine:
        return []
    
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT id, bond_code, bond_name, hit_price, scheme_json, lots, hit_time
                FROM auto_trade_hits
                WHERE status = 'pending' 
                  AND hit_time >= CURDATE()
                ORDER BY hit_time DESC
                LIMIT 20
            """))
            rows = result.fetchall()
            
            hits = []
            for row in rows:
                hits.append({
                    'id': row[0],
                    'code': row[1],
                    'name': row[2],
                    'price': float(row[3]),
                    'scheme': json.loads(row[4]) if row[4] else {},
                    'lots': row[5],
                    'hit_time': row[6].strftime('%H:%M:%S') if row[6] else '',
                })
            return hits
    except Exception as e:
        print(f"[hit_store] 查询pending失败: {e}")
        return []


def get_today_history() -> List[Dict]:
    """获取今日所有记录(含已完成的)"""
    engine = _get_engine()
    if not engine:
        return []
    
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT id, bond_code, bond_name, hit_price, status, 
                       fill_price, sell_price, hit_time, note
                FROM auto_trade_hits
                WHERE hit_time >= CURDATE()
                ORDER BY hit_time DESC
                LIMIT 50
            """))
            rows = result.fetchall()
            
            history = []
            for row in rows:
                history.append({
                    'id': row[0],
                    'code': row[1],
                    'name': row[2],
                    'hit_price': float(row[3]),
                    'status': row[4],
                    'fill_price': float(row[5]) if row[5] else 0,
                    'sell_price': float(row[6]) if row[6] else 0,
                    'hit_time': row[7].strftime('%H:%M:%S') if row[7] else '',
                    'note': row[8] or '',
                })
            return history
    except Exception as e:
        print(f"[hit_store] 查询历史失败: {e}")
        return []
