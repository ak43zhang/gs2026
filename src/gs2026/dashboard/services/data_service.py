"""
数据查询服务
负责从 MySQL 查询监控数据
"""
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, text
from typing import Optional, List, Dict, Any

from ..config import Config


class DataService:
    """数据服务类"""
    
    def __init__(self):
        """初始化数据库连接"""
        self.config = Config()
        self.engine = create_engine(
            self.config.SQLALCHEMY_DATABASE_URI,
            pool_recycle=3600,
            pool_pre_ping=True
        )
    
    def get_latest_date(self) -> str:
        """获取最新的监控日期"""
        today = datetime.now().strftime('%Y%m%d')
        return today
    
    def get_table_name(self, prefix: str, date: Optional[str] = None) -> str:
        """
        获取表名
        
        Args:
            prefix: 表名前缀（如 monitor_gp_top30）
            date: 日期字符串 YYYYMMDD，默认今天
        
        Returns:
            完整的表名
        """
        if date is None:
            date = self.get_latest_date()
        return f"{prefix}_{date}"
    
    def get_rising_ranking(self, limit: int = 30, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取上攻排行数据（股票）
        
        Args:
            limit: 返回条数
            date: 日期字符串，默认今天
        
        Returns:
            上攻排行列表
        """
        table_name = self.get_table_name('monitor_gp_top30', date)
        
        query = f"""
            SELECT 
                code,
                name,
                price_now,
                zf_30,
                momentum,
                amount_now,
                total_score,
                total_score_rank,
                time
            FROM {table_name}
            ORDER BY time DESC, total_score_rank ASC
            LIMIT {limit}
        """
        
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
                return df.to_dict('records')
        except Exception as e:
            print(f"查询上攻排行失败: {e}")
            return []
    
    def get_bond_rising_ranking(self, limit: int = 30, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取上攻排行数据（可转债）
        
        Args:
            limit: 返回条数
            date: 日期字符串，默认今天
        
        Returns:
            可转债上攻排行列表
        """
        table_name = self.get_table_name('monitor_zq_top30', date)
        
        query = f"""
            SELECT 
                code,
                name,
                price_now,
                zf_30,
                momentum,
                amount_now,
                total_score,
                total_score_rank,
                time
            FROM {table_name}
            ORDER BY time DESC, total_score_rank ASC
            LIMIT {limit}
        """
        
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
                return df.to_dict('records')
        except Exception as e:
            print(f"查询可转债排行失败: {e}")
            return []
    
    def get_market_stats(self, date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        获取大盘统计数据
        
        Args:
            date: 日期字符串，默认今天
        
        Returns:
            大盘统计数据
        """
        table_name = self.get_table_name('monitor_gp_apqd', date)
        
        query = f"""
            SELECT 
                time,
                cur_up,
                cur_down,
                cur_flat,
                cur_total,
                cur_up_ratio,
                cur_down_ratio,
                cur_up_down_ratio,
                min_up,
                min_down,
                min_up_ratio,
                min_down_ratio,
                strength_score,
                state,
                signal,
                base_score,
                trend_score
            FROM {table_name}
            ORDER BY time DESC
            LIMIT 1
        """
        
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
                if not df.empty:
                    return df.iloc[0].to_dict()
                return None
        except Exception as e:
            print(f"查询大盘数据失败: {e}")
            return None
    
    def get_market_history(self, limit: int = 100, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取大盘历史数据（用于图表）
        
        Args:
            limit: 返回条数
            date: 日期字符串，默认今天
        
        Returns:
            大盘历史数据列表
        """
        table_name = self.get_table_name('monitor_gp_apqd', date)
        
        query = f"""
            SELECT 
                time,
                cur_up_ratio,
                cur_down_ratio,
                strength_score,
                state,
                signal
            FROM {table_name}
            ORDER BY time ASC
            LIMIT {limit}
        """
        
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
                return df.to_dict('records')
        except Exception as e:
            print(f"查询大盘历史失败: {e}")
            return []
    
    def get_combine_ranking(self, limit: int = 30, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取股债联动排行数据
        
        Args:
            limit: 返回条数
            date: 日期字符串，默认今天
        
        Returns:
            股债联动排行列表
        """
        table_name = self.get_table_name('monitor_combine', date)
        
        query = f"""
            SELECT 
                code_gp,
                name_gp,
                zf_30,
                momentum,
                total_score_rank,
                code,
                name,
                zf_30_zq,
                momentum_zq,
                total_score_rank_zq,
                time
            FROM {table_name}
            ORDER BY time DESC, total_score_rank ASC
            LIMIT {limit}
        """
        
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
                return df.to_dict('records')
        except Exception as e:
            print(f"查询联动排行失败: {e}")
            return []
    
    def check_table_exists(self, table_name: str) -> bool:
        """
        检查表是否存在
        
        Args:
            table_name: 表名
        
        Returns:
            是否存在
        """
        query = f"""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = '{self.config.MYSQL_DATABASE}'
            AND table_name = '{table_name}'
        """
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                return result.scalar() == 1
        except Exception as e:
            print(f"检查表存在失败: {e}")
            return False
    
    def get_available_tables(self, prefix: str = 'monitor') -> List[str]:
        """
        获取可用的监控表列表
        
        Args:
            prefix: 表名前缀
        
        Returns:
            表名列表
        """
        query = f"""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = '{self.config.MYSQL_DATABASE}'
            AND table_name LIKE '{prefix}%%'
            ORDER BY table_name DESC
        """
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                return [row[0] for row in result]
        except Exception as e:
            print(f"获取表列表失败: {e}")
            return []
    
    def get_latest_update_time(self, table_prefix: str, date: Optional[str] = None) -> Optional[str]:
        """
        获取最新更新时间
        
        Args:
            table_prefix: 表名前缀
            date: 日期字符串
        
        Returns:
            最新时间字符串
        """
        table_name = self.get_table_name(table_prefix, date)
        
        if not self.check_table_exists(table_name):
            return None
        
        query = f"SELECT MAX(time) as latest_time FROM {table_name}"
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                row = result.fetchone()
                return row[0] if row and row[0] else None
        except Exception as e:
            print(f"获取最新时间失败: {e}")
            return None
