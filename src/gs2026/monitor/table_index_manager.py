"""
表索引管理模块
自动为监控数据表添加索引

使用方法:
    from gs2026.monitor.table_index_manager import TableIndexManager, auto_add_index
    
    # 方式1: 为指定日期的所有表添加索引
    TableIndexManager.add_index_for_date('20260331')
    
    # 方式2: 自动检测并添加索引（在save_dataframe后调用）
    auto_add_index('monitor_gp_sssj_20260331')
"""
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Set
from loguru import logger
from sqlalchemy import text

from gs2026.utils import mysql_util

mysql_tool = mysql_util.MysqlTool()

# 表索引配置
# key: 表名模式 (使用 {date} 作为日期占位符)
# value: 索引配置
INDEX_CONFIG: Dict[str, Dict] = {
    # 股票实时数据表
    'monitor_gp_sssj_{date}': {
        'indexes': [
            ('idx_code_time', 'stock_code, time'),  # 复合索引：代码+时间
            ('idx_time', 'time'),                     # 时间索引
        ]
    },
    # 债券实时数据表
    'monitor_zq_sssj_{date}': {
        'indexes': [
            ('idx_code_time', 'bond_code, time'),
            ('idx_time', 'time'),
        ]
    },
    # 行业实时数据表
    'monitor_hy_sssj_{date}': {
        'indexes': [
            ('idx_code_time', 'industry_code, time'),
            ('idx_time', 'time'),
        ]
    },
    # 股票Top30榜单
    'monitor_gp_top30_{date}': {
        'indexes': [
            ('idx_time', 'time'),
        ]
    },
    # 债券Top30榜单
    'monitor_zq_top30_{date}': {
        'indexes': [
            ('idx_time', 'time'),
        ]
    },
    # 行业Top30榜单
    'monitor_hy_top30_{date}': {
        'indexes': [
            ('idx_time', 'time'),
        ]
    },
    # 大盘强度
    'monitor_gp_apqd_{date}': {
        'indexes': [
            ('idx_time', 'time'),
        ]
    },
}


class TableIndexManager:
    """表索引管理器"""
    
    _indexed_tables: Set[str] = set()  # 已添加索引的表（内存缓存）
    _checked_tables: Set[str] = set()  # 已检查过的表（避免重复检查）
    
    @classmethod
    def add_index_for_date(cls, date_str: Optional[str] = None) -> Dict:
        """
        为指定日期的所有监控表添加索引
        
        Args:
            date_str: 日期 YYYYMMDD，默认今天
            
        Returns:
            操作结果统计
        """
        if date_str is None:
            date_str = datetime.now().strftime('%Y%m%d')
        
        logger.info(f"开始为 {date_str} 的监控表添加索引...")
        
        results = {
            'date': date_str,
            'total': 0,
            'success': 0,
            'skipped': 0,
            'failed': 0,
            'details': []
        }
        
        for table_pattern, config in INDEX_CONFIG.items():
            table_name = table_pattern.format(date=date_str)
            result = cls._add_index_to_table(table_name, config)
            results['total'] += 1
            
            if result['status'] == 'success':
                results['success'] += 1
            elif result['status'] == 'skipped':
                results['skipped'] += 1
            else:
                results['failed'] += 1
            
            results['details'].append(result)
        
        logger.info(
            f"{date_str} 索引添加完成: "
            f"成功={results['success']}, 跳过={results['skipped']}, 失败={results['failed']}"
        )
        return results
    
    @classmethod
    def _add_index_to_table(cls, table_name: str, config: Dict) -> Dict:
        """
        为单个表添加索引
        
        Returns:
            {'status': 'success'|'skipped'|'failed', 'table': str, 'message': str}
        """
        # 检查内存缓存
        if table_name in cls._indexed_tables:
            return {
                'status': 'skipped',
                'table': table_name,
                'message': '已在内存缓存中'
            }
        
        try:
            with mysql_tool.engine.connect() as conn:
                # 检查表是否存在
                result = conn.execute(text(f"""
                    SELECT COUNT(*) FROM information_schema.TABLES 
                    WHERE table_schema = DATABASE() AND table_name = '{table_name}'
                """))
                result = result.fetchall()
                
                if not result or result[0][0] == 0:
                    return {
                        'status': 'skipped',
                        'table': table_name,
                        'message': '表不存在'
                    }
                
                # 获取已有索引
                result = conn.execute(text(f"""
                    SELECT index_name FROM information_schema.STATISTICS 
                    WHERE table_schema = DATABASE() 
                    AND table_name = '{table_name}'
                """))
                existing_indexes = {row[0] for row in result.fetchall()}
                
                # 添加配置的索引
                added_count = 0
                for index_name, columns in config.get('indexes', []):
                    if index_name in existing_indexes:
                        continue
                    
                    try:
                        conn.execute(text(f"""
                            ALTER TABLE {table_name} 
                            ADD INDEX {index_name} ({columns})
                        """))
                        conn.commit()
                        logger.info(f"✓ {table_name}.{index_name} 创建成功")
                        added_count += 1
                    except Exception as e:
                        logger.warning(f"⚠ {table_name}.{index_name} 创建失败: {e}")
            
            if added_count > 0:
                cls._indexed_tables.add(table_name)
                return {
                    'status': 'success',
                    'table': table_name,
                    'message': f'添加了 {added_count} 个索引'
                }
            else:
                cls._indexed_tables.add(table_name)  # 已有索引，也加入缓存
                return {
                    'status': 'skipped',
                    'table': table_name,
                    'message': '所有索引已存在'
                }
            
        except Exception as e:
            logger.error(f"✗ {table_name} 索引添加失败: {e}")
            return {
                'status': 'failed',
                'table': table_name,
                'message': str(e)
            }
    
    @classmethod
    def should_add_index(cls, table_name: str) -> bool:
        """
        判断是否需要添加索引
        
        检查表名是否匹配配置的索引模式
        """
        # 已在缓存中
        if table_name in cls._indexed_tables:
            return False
        
        if table_name in cls._checked_tables:
            return False
        
        # 检查是否是监控表
        for pattern in INDEX_CONFIG.keys():
            if '{date}' in pattern:
                prefix = pattern.split('{date}')[0]
                suffix = pattern.split('{date}')[1] if len(pattern.split('{date}')) > 1 else ''
                
                if table_name.startswith(prefix) and table_name.endswith(suffix):
                    return True
        
        return False
    
    @classmethod
    def get_table_date(cls, table_name: str) -> Optional[str]:
        """
        从表名中提取日期
        
        Returns:
            YYYYMMDD 或 None
        """
        for pattern in INDEX_CONFIG.keys():
            if '{date}' in pattern:
                prefix = pattern.split('{date}')[0]
                suffix = pattern.split('{date}')[1] if len(pattern.split('{date}')) > 1 else ''
                
                if table_name.startswith(prefix) and table_name.endswith(suffix):
                    date_part = table_name[len(prefix):]
                    if suffix:
                        date_part = date_part[:-len(suffix)]
                    
                    # 验证日期格式
                    if len(date_part) == 8 and date_part.isdigit():
                        return date_part
        
        return None
    
    @classmethod
    def reset_cache(cls):
        """重置缓存（用于测试或每日重置）"""
        cls._indexed_tables.clear()
        cls._checked_tables.clear()
        logger.info("表索引管理器缓存已重置")


def auto_add_index(table_name: str) -> bool:
    """
    自动为表添加索引（如果符合配置）
    
    在 save_dataframe 等函数中调用
    
    Args:
        table_name: 表名
        
    Returns:
        是否成功添加索引
    """
    if not TableIndexManager.should_add_index(table_name):
        TableIndexManager._checked_tables.add(table_name)
        return False
    
    # 提取日期
    date_str = TableIndexManager.get_table_date(table_name)
    if not date_str:
        return False
    
    # 为该日期的所有表添加索引
    result = TableIndexManager.add_index_for_date(date_str)
    return result['success'] > 0


def add_index_on_first_write(table_name: str, time_str: str) -> bool:
    """
    在第一次写入时添加索引
    
    推荐在 09:30:00 第一次写入时调用
    
    Args:
        table_name: 表名
        time_str: 时间字符串 HH:MM:SS
        
    Returns:
        是否执行了索引添加
    """
    # 只在特定时间点触发（如 09:30:00）
    if time_str not in ['09:30:00', '09:30:03']:
        return False
    
    return auto_add_index(table_name)


# 便捷函数：检查表是否有索引
def check_table_indexes(table_name: str) -> Dict:
    """
    检查表的索引情况
    
    Returns:
        {'table': str, 'exists': bool, 'indexes': list}
    """
    try:
        with mysql_tool.engine.connect() as conn:
            # 检查表是否存在
            result = conn.execute(text(f"""
                SELECT COUNT(*) FROM information_schema.TABLES 
                WHERE table_schema = DATABASE() AND table_name = '{table_name}'
            """))
            result = result.fetchall()
            
            if not result or result[0][0] == 0:
                return {'table': table_name, 'exists': False, 'indexes': []}
            
            # 获取索引列表
            result = conn.execute(text(f"""
                SELECT index_name, column_name, seq_in_index
                FROM information_schema.STATISTICS 
                WHERE table_schema = DATABASE() 
                AND table_name = '{table_name}'
                ORDER BY index_name, seq_in_index
            """))
            
            indexes = {}
            for row in result.fetchall():
                index_name, column_name, seq = row
                if index_name not in indexes:
                    indexes[index_name] = []
                indexes[index_name].append(column_name)
            
            return {
                'table': table_name,
                'exists': True,
                'indexes': [
                    {'name': k, 'columns': v} 
                    for k, v in indexes.items()
                ]
            }
        
    except Exception as e:
        logger.error(f"检查表索引失败 {table_name}: {e}")
        return {'table': table_name, 'exists': False, 'indexes': [], 'error': str(e)}
