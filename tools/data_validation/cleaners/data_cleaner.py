"""数据清理器"""
from typing import Dict, List
import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import InvalidRecord, FixReport, ValidationReport


class DataCleaner:
    """数据清理器"""
    
    def __init__(self, mysql_engine, redis_client=None):
        self.engine = mysql_engine
        self.redis = redis_client
    
    def clean(self, validation_report: ValidationReport, interactive: bool = False) -> FixReport:
        """清理异常数据"""
        fix_report = FixReport(validation_report=validation_report)
        
        for record in validation_report.invalid_records:
            if interactive:
                # 交互模式：询问用户确认
                print(f"\n异常记录: {record.content_hash}")
                print(f"错误: {', '.join(record.errors)}")
                confirm = input("是否清理此记录? [y/n/q(退出)]: ").strip().lower()
                if confirm == 'q':
                    break
                if confirm != 'y':
                    continue
            
            try:
                # 1. 删除分析表数据
                self._delete_analysis_record(record)
                fix_report.deleted_mysql += 1
                
                # 2. 清理Redis缓存
                if self.redis:
                    self._delete_redis_cache(record)
                    fix_report.deleted_redis += 1
                
                # 3. 标记源表重跑
                if record.source_table:
                    self._mark_source_table(record)
                    fix_report.marked_source += 1
                    
            except Exception as e:
                error_msg = f"清理记录 {record.content_hash} 失败: {str(e)}"
                fix_report.errors.append(error_msg)
                print(f"  ❌ {error_msg}")
        
        return fix_report
    
    def _delete_analysis_record(self, record: InvalidRecord):
        """删除分析表记录"""
        from sqlalchemy import text
        
        sql = f"""
            DELETE FROM {record.table_name}
            WHERE content_hash = '{record.content_hash}'
        """
        
        with self.engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()
        
        print(f"  ✅ 已删除分析表记录: {record.content_hash}")
    
    def _delete_redis_cache(self, record: InvalidRecord):
        """删除Redis缓存"""
        if not self.redis:
            return
        
        # 构建Redis key模式并删除
        # 这里需要根据实际Redis key格式调整
        patterns = [
            f"news:detail:{record.content_hash}",
            f"news:timeline:*:{record.content_hash}",
        ]
        
        for pattern in patterns:
            try:
                self.redis.delete(pattern)
            except Exception:
                pass
        
        print(f"  ✅ 已清理Redis缓存: {record.content_hash}")
    
    def _mark_source_table(self, record: InvalidRecord):
        """标记源表待重跑"""
        from sqlalchemy import text
        
        # 解析源表（可能有多个，用/分隔）
        source_tables = record.source_table.split('/')
        
        for source_table in source_tables:
            if not source_table:
                continue
                
            sql = f"""
                UPDATE {source_table}
                SET analysis = 'pending'
                WHERE content_hash = '{record.content_hash}'
            """
            
            try:
                with self.engine.connect() as conn:
                    result = conn.execute(text(sql))
                    conn.commit()
                    if result.rowcount > 0:
                        print(f"  ✅ 已标记源表 {source_table}: {record.content_hash}")
            except Exception as e:
                print(f"  ⚠️ 标记源表 {source_table} 失败: {e}")
