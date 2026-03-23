"""
数据查询服务
负责从 Redis 和 MySQL 查询监控数据
"""
import pandas as pd
import json
from datetime import datetime
from sqlalchemy import create_engine, text
from typing import Optional, List, Dict, Any

import redis

from ..config import Config
from gs2026.utils import redis_util


class DataService:
    """数据服务类"""
    
    # 资产类型配置
    ASSET_CONFIG = {
        'stock': {
            'table_prefix': 'monitor_gp_top30',
            'redis_rank_key': 'rank:stock:code',
            'redis_name_key': 'rank:stock:code_name',
            'code_col': 'code',
            'name_col': 'name'
        },
        'bond': {
            'table_prefix': 'monitor_zq_top30',
            'redis_rank_key': 'rank:bond:code',
            'redis_name_key': 'rank:bond:code_name',
            'code_col': 'code',
            'name_col': 'name'
        },
        'industry': {
            'table_prefix': 'monitor_hy_top30',
            'redis_rank_key': 'rank:industry:code',
            'redis_name_key': 'rank:industry:code_name',
            'code_col': 'code',
            'name_col': 'name'
        }
    }
    
    def __init__(self):
        """初始化数据库连接"""
        self.config = Config()
        
        # MySQL 连接
        self.engine = create_engine(
            self.config.SQLALCHEMY_DATABASE_URI,
            pool_recycle=3600,
            pool_pre_ping=True
        )
        
        # 初始化 Redis 连接
        try:
            redis_util.init_redis(
                host=self.config.REDIS_HOST,
                port=self.config.REDIS_PORT,
                db=self.config.REDIS_DB,
                decode_responses=False
            )
            self.redis_available = True
        except Exception as e:
            print(f"Redis 连接失败: {e}")
            self.redis_available = False
    
    def get_latest_date(self) -> str:
        """获取最新的监控日期"""
        today = datetime.now().strftime('%Y%m%d')
        return today
    
    def get_table_name(self, prefix: str, date: Optional[str] = None) -> str:
        """获取表名"""
        if date is None:
            date = self.get_latest_date()
        return f"{prefix}_{date}"
    
    def get_market_stats(self, date: Optional[str] = None, 
                        use_mysql: bool = False) -> Dict[str, Any]:
        """
        获取大盘统计数据（股票 + 债券）
        
        优先从 Redis 查询，如果 Redis 没有且 use_mysql=True，则查询 MySQL
        要求获取同一时间的股票和债券数据
        
        Args:
            date: 日期字符串，默认今天
            use_mysql: 是否允许查询 MySQL，默认 False（只查 Redis）
        
        Returns:
            {'stock': {...}, 'bond': {...}}
        """
        if date is None:
            date = self.get_latest_date()
        
        result = {'stock': None, 'bond': None}
        
        # 表名格式: monitor_gp_apqd_{date} 和 monitor_zq_apqd_{date}
        stock_table = f"monitor_gp_apqd_{date}"
        bond_table = f"monitor_zq_apqd_{date}"
        
        # 1. 优先从 Redis 查询
        if self.redis_available:
            try:
                # 使用 redis_util.load_dataframe_by_offset 获取最新数据
                stock_df = redis_util.load_dataframe_by_offset(stock_table, offset=0, use_compression=False)
                bond_df = redis_util.load_dataframe_by_offset(bond_table, offset=0, use_compression=False)
                
                if stock_df is not None and not stock_df.empty:
                    # 取最新一条记录
                    result['stock'] = stock_df.iloc[-1].to_dict()
                    print(f"从 Redis 获取股票大盘数据: {stock_table}")
                
                if bond_df is not None and not bond_df.empty:
                    result['bond'] = bond_df.iloc[-1].to_dict()
                    print(f"从 Redis 获取债券大盘数据: {bond_table}")
                
                # 如果 Redis 都有数据，直接返回
                if result['stock'] and result['bond']:
                    return result
                    
            except Exception as e:
                print(f"Redis 查询失败: {e}")
        
        # 2. 如果 use_mysql=False，直接返回（可能部分为空）
        if not use_mysql:
            print("Redis 无数据且 use_mysql=False，返回空")
            return result
        
        # 3. 查询 MySQL
        # 获取最新时间（从股票表）
        latest_time = self._get_latest_time('monitor_gp_apqd', date)
        
        if latest_time:
            # 查询同一时间的数据
            result['stock'] = self._query_market_by_time('monitor_gp_apqd', latest_time, date)
            result['bond'] = self._query_market_by_time('monitor_zq_apqd', latest_time, date)
        
        return result
    
    def _get_latest_time(self, table_prefix: str, date: Optional[str] = None) -> Optional[str]:
        """获取最新时间"""
        table_name = self.get_table_name(table_prefix, date)
        
        query = f"SELECT MAX(time) as latest_time FROM {table_name}"
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                row = result.fetchone()
                return row[0] if row and row[0] else None
        except Exception as e:
            print(f"获取最新时间失败: {e}")
            return None
    
    def _query_market_by_time(self, table_prefix: str, time: str, 
                              date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """按时间查询大盘数据"""
        table_name = self.get_table_name(table_prefix, date)
        
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
                `signal`,
                base_score,
                trend_score
            FROM {table_name}
            WHERE time = '{time}'
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
    
    def get_rising_ranking(self, asset_type: str = 'stock', limit: int = 30, 
                          date: Optional[str] = None, use_mysql: bool = False) -> List[Dict[str, Any]]:
        """
        获取上攻排行数据（股票/债券/行业通用）
        
        优先从 Redis 查询最新排行榜，如果 Redis 没有且 use_mysql=True，则查询 MySQL
        历史日期优先从 rank_{asset_type} 表查询收盘排行数据
        
        Args:
            asset_type: 资产类型，'stock' | 'bond' | 'industry'
            limit: 返回条数
            date: 日期字符串，默认今天
            use_mysql: 是否允许查询 MySQL，False 则只查 Redis
        
        Returns:
            上攻排行列表
        """
        if asset_type not in self.ASSET_CONFIG:
            print(f"不支持的资产类型: {asset_type}")
            return []
        
        if date is None:
            date = self.get_latest_date()
        
        config = self.ASSET_CONFIG[asset_type]
        
        # 判断是否为历史日期
        today = self.get_latest_date()
        is_history = (date != today)
        
        result = []
        
        # 1. 今天：优先查 Redis（获取最新累积排行）
        #    历史日期：跳过 Redis，直接查 MySQL 的 rank 表
        if not is_history and self.redis_available:
            try:
                redis_code_key = config['redis_rank_key']
                redis_name_key = config['redis_name_key']
                
                # 获取排行榜（按分数降序）
                rank_data = redis_util._get_redis_client().zrevrange(redis_code_key, 0, limit - 1, withscores=True)
                
                if rank_data:
                    for code, score in rank_data:
                        count = int(score)
                        # 获取名称
                        name = redis_util._get_redis_client().hget(redis_name_key, code)
                        name = name.decode('utf-8') if isinstance(name, bytes) else (name or '')
                        code = code.decode('utf-8') if isinstance(code, bytes) else code
                        
                        result.append({
                            'code': code,
                            'name': name,
                            'count': count,
                            'type': asset_type,
                            'date': date,
                            'rank': len(result) + 1
                        })
                    
                    print(f"从 Redis 获取 {asset_type} 上攻排行: {len(result)} 条")
                    return result
                
            except Exception as e:
                print(f"Redis 查询失败: {e}")
        
        # 2. 如果 use_mysql=False，直接返回空
        if not use_mysql:
            print(f"Redis 无数据且 use_mysql=False，返回空")
            return []
        
        # 3. 历史日期：优先从 rank_{asset_type} 表查询收盘排行
        if is_history:
            try:
                rank_table = f"rank_{asset_type}"
                query = f"""
                    SELECT code, name, count, date
                    FROM {rank_table}
                    WHERE date = '{date}'
                    ORDER BY count DESC
                    LIMIT {limit}
                """
                with self.engine.connect() as conn:
                    df = pd.read_sql(query, conn)
                    if not df.empty:
                        for idx, row in df.iterrows():
                            result.append({
                                'code': row['code'],
                                'name': row['name'],
                                'count': int(row['count']),
                                'type': asset_type,
                                'date': row['date'],
                                'rank': idx + 1
                            })
                        print(f"从 MySQL rank 表获取 {asset_type} 历史排行: {len(result)} 条")
                        return result
            except Exception as e:
                print(f"查询 rank 表失败: {e}，尝试查询实时数据表")
        
        # 4. 查询实时数据表（今天的实时数据或历史日期的 fallback）
        table_name = self.get_table_name(config['table_prefix'], date)
        
        query = f"""
            SELECT 
                {config['code_col']} as code,
                {config['name_col']} as name,
                price_now,
                zf_30,
                momentum,
                amount_now,
                total_score,
                total_score_rank,
                time
            FROM {table_name}
            ORDER BY time DESC, total_score_rank ASC
            LIMIT {limit * 3}
        """
        
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
                
                if not df.empty:
                    # 统计出现次数（模拟 update_rank_redis 的逻辑）
                    code_counts = df['code'].value_counts()
                    
                    for rank, (code, count) in enumerate(code_counts.head(limit).items(), 1):
                        name = df.loc[df['code'] == code, 'name'].iloc[0]
                        row_data = {
                            'code': code,
                            'name': name,
                            'count': int(count),
                            'type': asset_type,
                            'date': date,
                            'rank': rank
                        }
                        
                        # 添加额外字段（如果有）
                        if 'price_now' in df.columns:
                            row_data['latest_price'] = df.loc[df['code'] == code, 'price_now'].iloc[0]
                        if 'zf_30' in df.columns:
                            row_data['zf_30'] = df.loc[df['code'] == code, 'zf_30'].iloc[0]
                        if 'momentum' in df.columns:
                            row_data['momentum'] = df.loc[df['code'] == code, 'momentum'].iloc[0]
                        if 'total_score' in df.columns:
                            row_data['total_score'] = df.loc[df['code'] == code, 'total_score'].iloc[0]
                        
                        result.append(row_data)
                    
                    print(f"从 MySQL 实时表获取 {asset_type} 上攻排行: {len(result)} 条")
                    
                    # 同步到 Redis（供下次快速查询）
                    if self.redis_available and not is_history:
                        redis_util.update_rank_redis(df, rank_name=asset_type, 
                                                     code_col=config['code_col'],
                                                     name_col=config['name_col'])
                
                return result
                
        except Exception as e:
            print(f"查询 {asset_type} 上攻排行失败: {e}")
            return []
    
    # 快捷方法
    def get_stock_ranking(self, limit: int = 30, date: Optional[str] = None, 
                         use_mysql: bool = False) -> List[Dict[str, Any]]:
        return self.get_rising_ranking(asset_type='stock', limit=limit, date=date, use_mysql=use_mysql)
    
    def get_bond_ranking(self, limit: int = 30, date: Optional[str] = None,
                        use_mysql: bool = False) -> List[Dict[str, Any]]:
        return self.get_rising_ranking(asset_type='bond', limit=limit, date=date, use_mysql=use_mysql)
    
    def get_industry_ranking(self, limit: int = 30, date: Optional[str] = None,
                            use_mysql: bool = False) -> List[Dict[str, Any]]:
        return self.get_rising_ranking(asset_type='industry', limit=limit, date=date, use_mysql=use_mysql)
    
    def get_all_rankings(self, limit: int = 30, date: Optional[str] = None,
                        use_mysql: bool = False) -> Dict[str, List[Dict[str, Any]]]:
        """获取所有排行榜"""
        return {
            'stock': self.get_stock_ranking(limit, date, use_mysql),
            'bond': self.get_bond_ranking(limit, date, use_mysql),
            'industry': self.get_industry_ranking(limit, date, use_mysql)
        }
