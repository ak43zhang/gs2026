"""
扩展指标数据访问层 - 透明处理JSON字段

设计原则:
- 兼容旧表：无ext_indicators字段时返回空值
- 增量更新：支持合并更新，不覆盖其他扩展指标
- 高性能：批量操作，减少数据库往返
"""

import json
import logging
from typing import Dict, List, Any, Optional, Union
from sqlalchemy import text

logger = logging.getLogger(__name__)


class ExtIndicatorDAO:
    """扩展指标DAO - 透明处理JSON"""
    
    def __init__(self, engine):
        self.engine = engine
        self._has_ext_column_cache = {}  # 缓存表是否有ext_indicators字段
    
    def _check_ext_column_exists(self, table_name: str) -> bool:
        """检查表是否有ext_indicators字段（带缓存）"""
        if table_name in self._has_ext_column_cache:
            return self._has_ext_column_cache[table_name]
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(f"""
                    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = '{table_name}'
                    AND COLUMN_NAME = 'ext_indicators'
                """))
                exists = result.scalar() > 0
                self._has_ext_column_cache[table_name] = exists
                return exists
        except Exception as e:
            logger.warning(f"检查ext_indicators字段失败: {e}")
            return False
    
    def save_ext_indicators(self, table_name: str, 
                           trade_date: int, time: int, bond_code: str,
                           ext_indicators: Dict[str, Any]):
        """
        保存扩展指标（只改ext_indicators字段）
        
        兼容旧表：如果表没有ext_indicators字段，则静默跳过
        """
        if not self._check_ext_column_exists(table_name):
            # 旧表，直接保存到独立字段
            return self._save_to_legacy_fields(
                table_name, trade_date, time, bond_code, ext_indicators
            )
        
        sql = text(f"""
            UPDATE {table_name}
            SET ext_indicators = :ext_json
            WHERE trade_date = :date AND time = :time AND bond_code = :code
        """)
        try:
            with self.engine.connect() as conn:
                conn.execute(sql, {
                    'ext_json': json.dumps(ext_indicators, ensure_ascii=False),
                    'date': trade_date,
                    'time': time,
                    'code': bond_code
                })
                conn.commit()
        except Exception as e:
            logger.error(f"保存扩展指标失败: {e}")
    
    def _save_to_legacy_fields(self, table_name: str,
                               trade_date: int, time: int, bond_code: str,
                               ext_indicators: Dict[str, Any]):
        """保存到独立字段（兼容旧表）"""
        # 构建动态UPDATE
        update_fields = []
        params = {'date': trade_date, 'time': time, 'code': bond_code}
        
        field_mapping = {
            'weighted_slope_2m': 'weighted_slope_2m',
            'change_1m_pct': 'change_1m_pct',
            'price_acceleration': 'price_acceleration',
        }
        
        for ext_key, db_field in field_mapping.items():
            if ext_key in ext_indicators:
                update_fields.append(f"{db_field} = :{ext_key}")
                params[ext_key] = ext_indicators[ext_key]
        
        if not update_fields:
            return
        
        sql = text(f"""
            UPDATE {table_name}
            SET {', '.join(update_fields)}
            WHERE trade_date = :date AND time = :time AND bond_code = :code
        """)
        try:
            with self.engine.connect() as conn:
                conn.execute(sql, params)
                conn.commit()
        except Exception as e:
            logger.error(f"保存独立字段失败: {e}")
    
    def merge_ext_indicators(self, table_name: str,
                            trade_date: int, time: int, bond_code: str,
                            new_indicators: Dict[str, Any]):
        """
        合并扩展指标（增量更新）
        
        不会覆盖ext_indicators中的其他字段
        """
        if not self._check_ext_column_exists(table_name):
            # 旧表，直接保存到独立字段
            return self._save_to_legacy_fields(
                table_name, trade_date, time, bond_code, new_indicators
            )
        
        # 读取现有
        existing = self.get_ext_indicators(table_name, trade_date, time, bond_code)
        # 合并
        existing.update(new_indicators)
        # 保存
        self.save_ext_indicators(table_name, trade_date, time, bond_code, existing)
    
    def get_ext_indicators(self, table_name: str,
                          trade_date: int, time: int, 
                          bond_code: str) -> Dict[str, Any]:
        """
        获取扩展指标
        
        兼容旧表：如果表没有ext_indicators字段，则从独立字段读取
        """
        if not self._check_ext_column_exists(table_name):
            # 旧表，从独立字段读取
            return self._get_from_legacy_fields(table_name, trade_date, time, bond_code)
        
        sql = text(f"""
            SELECT ext_indicators FROM {table_name}
            WHERE trade_date = :date AND time = :time AND bond_code = :code
        """)
        try:
            with self.engine.connect() as conn:
                result = conn.execute(sql, {
                    'date': trade_date, 'time': time, 'code': bond_code
                }).fetchone()
                
                if result and result[0]:
                    try:
                        return json.loads(result[0])
                    except json.JSONDecodeError:
                        logger.warning(f"JSON解析失败: {result[0][:100]}")
                return {}
        except Exception as e:
            logger.error(f"获取扩展指标失败: {e}")
            return {}
    
    def _get_from_legacy_fields(self, table_name: str,
                               trade_date: int, time: int, 
                               bond_code: str) -> Dict[str, Any]:
        """从独立字段读取（兼容旧表）"""
        sql = text(f"""
            SELECT weighted_slope_2m, change_1m_pct, price_acceleration
            FROM {table_name}
            WHERE trade_date = :date AND time = :time AND bond_code = :code
        """)
        try:
            with self.engine.connect() as conn:
                result = conn.execute(sql, {
                    'date': trade_date, 'time': time, 'code': bond_code
                }).fetchone()
                
                if result:
                    return {
                        'weighted_slope_2m': result[0] or 0.0,
                        'change_1m_pct': result[1] or 0.0,
                        'price_acceleration': result[2] or 0.0,
                    }
                return {}
        except Exception as e:
            logger.error(f"获取独立字段失败: {e}")
            return {}
    
    def get_ext_indicator(self, table_name: str,
                         trade_date: int, time: int, bond_code: str,
                         indicator_code: str, default: Any = 0) -> Any:
        """获取单个扩展指标"""
        indicators = self.get_ext_indicators(table_name, trade_date, time, bond_code)
        return indicators.get(indicator_code, default)
    
    def batch_get_ext_indicators(self, table_name: str,
                                trade_date: int, time: int,
                                bond_codes: List[str]) -> Dict[str, Dict]:
        """批量获取扩展指标"""
        if not bond_codes:
            return {}
        
        if not self._check_ext_column_exists(table_name):
            # 旧表，逐个查询
            return {
                code: self._get_from_legacy_fields(table_name, trade_date, time, code)
                for code in bond_codes
            }
        
        placeholders = ','.join([f"'{c}'" for c in bond_codes])
        sql = text(f"""
            SELECT bond_code, ext_indicators FROM {table_name}
            WHERE trade_date = :date AND time = :time
            AND bond_code IN ({placeholders})
        """)
        try:
            with self.engine.connect() as conn:
                result = conn.execute(sql, {'date': trade_date, 'time': time})
                return {
                    row[0]: json.loads(row[1]) if row[1] else {}
                    for row in result
                }
        except Exception as e:
            logger.error(f"批量获取扩展指标失败: {e}")
            return {}
    
    def query_by_ext_indicator(self, table_name: str,
                              trade_date: int, time: int,
                              indicator_code: str,
                              operator: str = '>',
                              value: Any = 0) -> List[Dict]:
        """
        根据扩展指标查询
        
        支持操作符: >, <, >=, <=, =, !=
        """
        # 安全检查操作符
        allowed_ops = ['>', '<', '>=', '<=', '=', '!=']
        if operator not in allowed_ops:
            raise ValueError(f"不支持的操作符: {operator}")
        
        if not self._check_ext_column_exists(table_name):
            # 旧表，从独立字段查询
            field_mapping = {
                'weighted_slope_2m': 'weighted_slope_2m',
                'change_1m_pct': 'change_1m_pct',
                'price_acceleration': 'price_acceleration',
            }
            db_field = field_mapping.get(indicator_code, indicator_code)
            sql = text(f"""
                SELECT *, {db_field} as {indicator_code}
                FROM {table_name}
                WHERE trade_date = :date AND time = :time
                AND {db_field} IS NOT NULL
                AND {db_field} {operator} :value
            """)
        else:
            # 新表，从JSON查询
            sql = text(f"""
                SELECT *, 
                       JSON_EXTRACT(ext_indicators, '$.{indicator_code}') as {indicator_code}
                FROM {table_name}
                WHERE trade_date = :date AND time = :time
                AND JSON_EXTRACT(ext_indicators, '$.{indicator_code}') IS NOT NULL
                AND JSON_EXTRACT(ext_indicators, '$.{indicator_code}') {operator} :value
            """)
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(sql, {
                    'date': trade_date, 'time': time, 'value': value
                })
                rows = [dict(row._mapping) for row in result]
                
                # 处理ext_indicators字段
                for row in rows:
                    if 'ext_indicators' in row and row['ext_indicators']:
                        try:
                            ext = json.loads(row['ext_indicators'])
                            row.update({f"ext_{k}": v for k, v in ext.items()})
                        except:
                            pass
                
                return rows
        except Exception as e:
            logger.error(f"查询扩展指标失败: {e}")
            return []
