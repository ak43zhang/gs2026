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
            'code_col': 'code',
            'name_col': 'name'
        },
        'bond': {
            'table_prefix': 'monitor_zq_top30',
            'code_col': 'code',
            'name_col': 'name'
        },
        'industry': {
            'table_prefix': 'monitor_hy_top30',
            'code_col': 'code',
            'name_col': 'name'
        }
    }

    def _get_redis_keys(self, asset_type: str, date: str) -> Dict[str, str]:
        """
        动态生成带日期后缀的 Redis key
        
        Args:
            asset_type: 资产类型，'stock' | 'bond' | 'industry'
            date: 日期字符串 YYYYMMDD
        
        Returns:
            {'rank_key': 'rank:xxx:code_YYYYMMDD', 'name_key': 'rank:xxx:code_name_YYYYMMDD'}
        """
        return {
            'rank_key': f'rank:{asset_type}:code_{date}',
            'name_key': f'rank:{asset_type}:code_name_{date}'
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

        # 附加数据库分析器（如果启用）
        try:
            from gs2026.dashboard2.middleware.db_profiler import DBProfiler
            import os
            import yaml
            from pathlib import Path

            # 从 settings.yaml 读取配置
            profiler_config = {}
            try:
                config_path = Path(__file__).parent.parent.parent.parent.parent / 'configs' / 'settings.yaml'
                if config_path.exists():
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f)
                        profiler_config = config.get('db_profiler', {})
            except Exception:
                pass

            # 检查是否启用
            enabled = os.environ.get('ENABLE_DB_PROFILER')
            if enabled is not None:
                enabled = enabled == '1'
            else:
                enabled = profiler_config.get('enabled', False)

            # 创建DBProfiler实例并传入enabled参数，确保正确初始化
            profiler = DBProfiler(enabled=enabled)
            if enabled:
                profiler.attach_to_engine(self.engine)
        except Exception as e:
            print(f"[DataService] 附加数据库分析器失败: {e}")
        
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
    
    def get_timestamps(self, date: Optional[str] = None, use_mysql: bool = True) -> List[str]:
        """
        获取指定日期的所有数据时间点
        优先 Redis，Redis 无数据则回退到 MySQL
        
        Args:
            date: 日期 YYYYMMDD，默认今天
            use_mysql: 是否允许查询 MySQL 回退
        
        Returns:
            时间点列表（已排序），如 ['09:30:00', '09:30:03', ...]
        """
        if date is None:
            date = self.get_latest_date()
        
        # 1. 先查 Redis
        if self.redis_available:
            try:
                client = redis_util._get_redis_client()
                # 股票和债券的时间戳应该一致，优先查股票
                ts_key = f"monitor_gp_apqd_{date}:timestamps"
                all_ts = client.lrange(ts_key, 0, -1)
                
                if all_ts:
                    # 解码 + 去重 + 排序
                    timestamps = sorted(set(
                        t.decode('utf-8') if isinstance(t, bytes) else t
                        for t in all_ts
                    ))
                    return timestamps
            except Exception as e:
                print(f"Redis 获取 timestamps 失败: {e}")
        
        # 2. Redis 无数据，回退到 MySQL
        if use_mysql:
            try:
                # 查询股票表的时间点
                table_name = f"monitor_gp_apqd_{date}"
                sql = f"SELECT DISTINCT time FROM {table_name} ORDER BY time"
                
                with self.engine.connect() as conn:
                    df = pd.read_sql(sql, conn)
                
                if not df.empty:
                    timestamps = df['time'].tolist()
                    return timestamps
            except Exception as e:
                print(f"MySQL 获取 timestamps 失败: {e}")
        
        return []
    
    def get_market_stats(self, date: Optional[str] = None, 
                        use_mysql: bool = False,
                        time_str: Optional[str] = None) -> Dict[str, Any]:
        """
        获取大盘统计数据（股票 + 债券）
        
        Args:
            date: 日期字符串，默认今天
            use_mysql: 是否允许查询 MySQL
            time_str: 指定时间 HH:MM:SS，None 表示最新
        
        Returns:
            {'stock': {...}, 'bond': {...}}
        """
        if date is None:
            date = self.get_latest_date()
        
        result = {'stock': None, 'bond': None}
        
        # 表名格式: monitor_gp_apqd_{date} 和 monitor_zq_apqd_{date}
        stock_table = f"monitor_gp_apqd_{date}"
        bond_table = f"monitor_zq_apqd_{date}"
        
        # 如果指定了时间，直接按 key 从 Redis 读取
        if time_str and self.redis_available:
            try:
                stock_df = redis_util.load_dataframe_by_key(f"{stock_table}:{time_str}", use_compression=False)
                bond_df = redis_util.load_dataframe_by_key(f"{bond_table}:{time_str}", use_compression=False)
                
                if stock_df is not None and not stock_df.empty:
                    result['stock'] = stock_df.iloc[-1].where(stock_df.iloc[-1].notna(), None).to_dict()
                if bond_df is not None and not bond_df.empty:
                    result['bond'] = bond_df.iloc[-1].where(bond_df.iloc[-1].notna(), None).to_dict()
                
                if result['stock'] or result['bond']:
                    return result
            except Exception as e:
                print(f"按时间查询 Redis 失败: {e}")
            
            # fallback 到 MySQL
            if use_mysql:
                result['stock'] = self._query_market_by_time('monitor_gp_apqd', time_str, date)
                result['bond'] = self._query_market_by_time('monitor_zq_apqd', time_str, date)
            return result
        
        # 1. 无指定时间，优先从 Redis 查询最新
        if self.redis_available:
            try:
                # 使用 redis_util.load_dataframe_by_offset 获取最新数据
                stock_df = redis_util.load_dataframe_by_offset(stock_table, offset=0, use_compression=False)
                bond_df = redis_util.load_dataframe_by_offset(bond_table, offset=0, use_compression=False)
                
                if stock_df is not None and not stock_df.empty:
                    # 取最新一条记录，将 NaN 替换为 None（确保 JSON 序列化为 null）
                    row = stock_df.iloc[-1].where(stock_df.iloc[-1].notna(), None).to_dict()
                    result['stock'] = row
                    print(f"从 Redis 获取股票大盘数据: {stock_table}")
                
                if bond_df is not None and not bond_df.empty:
                    row = bond_df.iloc[-1].where(bond_df.iloc[-1].notna(), None).to_dict()
                    result['bond'] = row
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
        
        # 动态生成带日期的 Redis key
        redis_keys = self._get_redis_keys(asset_type, date)
        redis_code_key = redis_keys['rank_key']
        redis_name_key = redis_keys['name_key']
        
        # 1. 今天：优先查 Redis（获取最新累积排行）
        #    历史日期：跳过 Redis，直接查 MySQL 的 rank 表
        if not is_history and self.redis_available:
            try:
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

    def get_ranking_at_time(self, asset_type: str = 'stock', limit: int = 15,
                            date: Optional[str] = None, 
                            time_str: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取某个时间点（截止到该时间）的上攻排行
        
        从 MySQL top30 表中统计截止到 time_str 的累计出现次数排行。
        
        Args:
            asset_type: 资产类型 'stock' | 'bond' | 'industry'
            limit: 返回条数
            date: 日期 YYYYMMDD，默认今天
            time_str: 截止时间 HH:MM:SS，默认 None 表示全部
        
        Returns:
            排行列表 [{'code','name','count','rank','type','date'}, ...]
        """
        if asset_type not in self.ASSET_CONFIG:
            return []
        
        if date is None:
            date = self.get_latest_date()
        
        config = self.ASSET_CONFIG[asset_type]
        table_name = self.get_table_name(config['table_prefix'], date)
        
        time_filter = f"AND time <= '{time_str}'" if time_str else ""
        
        query = f"""
            SELECT {config['code_col']} AS code, 
                   {config['name_col']} AS name,
                   COUNT(*) AS count
            FROM {table_name}
            WHERE 1=1 {time_filter}
            GROUP BY {config['code_col']}, {config['name_col']}
            ORDER BY count DESC
            LIMIT {limit}
        """
        
        result = []
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
                if not df.empty:
                    for idx, row in df.iterrows():
                        result.append({
                            'code': str(row['code']),
                            'name': str(row['name']),
                            'count': int(row['count']),
                            'type': asset_type,
                            'date': date,
                            'rank': idx + 1
                        })
                    time_desc = f"截止{time_str}" if time_str else "全天"
                    print(f"从 MySQL 获取 {asset_type} {time_desc} 排行: {len(result)} 条")
        except Exception as e:
            print(f"查询 {asset_type} 时间排行失败: {e}")
        
        return result

    def get_combine_ranking(self, limit: int = 50, date: Optional[str] = None, time_str: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取股债联动信号数据（monitor_combine 表）
        
        优先从 Redis 获取最新数据，如果没有则查 MySQL。
        返回按 time 倒序排列的记录。
        
        Args:
            limit: 返回条数
            date: 日期字符串 YYYYMMDD，默认今天
            time_str: 时间过滤，只返回该时间之前的数据（包含该时间）
        
        Returns:
            信号数据列表
        """
        if date is None:
            date = self.get_latest_date()
        
        table_name = f"monitor_combine_{date}"
        result = []
        
        # 1. 尝试从 Redis 获取（汇总多个时间点）
        if self.redis_available:
            try:
                client = redis_util._get_redis_client()
                ts_list_key = f"{table_name}:timestamps"
                total_ts = client.llen(ts_list_key)
                
                if total_ts > 0:
                    # 获取最近的时间戳列表（限制18个，平衡数据量和性能）
                    all_ts = client.lrange(ts_list_key, 0, min(total_ts, 18) - 1)
                    
                    seen_keys = set()  # 初始化去重集合，避免同一债券重复添加
                    
                    for ts_data in all_ts:
                        ts = ts_data.decode('utf-8') if isinstance(ts_data, bytes) else ts_data
                        
                        # 时间过滤：只返回 time_str 之前的数据
                        if time_str and ts > time_str:
                            continue
                        
                        key = f"{table_name}:{ts}"
                        df = redis_util.load_dataframe_by_key(key, use_compression=False)
                        
                        if df is not None and not df.empty:
                            for _, row in df.iterrows():
                                # 用 code+name+time 去重
                                dedup_key = f"{row.get('code', '')}_{row.get('name', '')}_{row.get('time', ts)}"
                                if dedup_key in seen_keys:
                                    continue
                                seen_keys.add(dedup_key)
                                
                                # 计算买入价格和卖出价格
                                # 买入价格 = 价格保留1位小数 + 0.1
                                # 卖出价格 = 买入价格 + 0.4
                                price_now = row.get('price_now_zq', row.get('price_now', 0))
                                buy_price = None
                                sell_price = None
                                if price_now:
                                    price_1decimal = round(price_now, 1)  # 保留1位小数
                                    buy_price = round(price_1decimal + 0.1, 2)  # 买入价格
                                    sell_price = round(buy_price + 0.4, 2)  # 卖出价格
                                
                                record = {
                                    'time': row.get('time', ts),
                                    'code': str(row.get('code', '')).zfill(6) if row.get('code') else '',
                                    'name': row.get('name', ''),
                                    'code_gp': str(row.get('code_gp', '')).zfill(6) if row.get('code_gp') else '',
                                    'name_gp': row.get('name_gp', ''),
                                    'price_now_zq': price_now,
                                    'buy_price': buy_price,
                                    'sell_price': sell_price,
                                    'zf_30': row.get('zf_30', None),
                                    'zf_30_zq': row.get('zf_30_zq', None),
                                }
                                result.append(record)
                        
                        if len(result) >= limit:
                            break
                    
                    if result:
                        # 按 time 倒序
                        result.sort(key=lambda x: x.get('time', ''), reverse=True)
                        result = result[:limit]
                        print(f"从 Redis 获取 combine 数据: {len(result)} 条")
                        return result
                        
            except Exception as e:
                print(f"Redis 查询 combine 失败: {e}")
        
        # 2. 查 MySQL
        try:
            # 构建查询，支持时间过滤
            if time_str:
                query = f"""
                    SELECT time, code, name, code_gp, name_gp, 
                           price_now_zq, zf_30, zf_30_zq
                    FROM {table_name}
                    WHERE time <= '{time_str}'
                    ORDER BY time DESC
                    LIMIT {limit}
                """
            else:
                query = f"""
                    SELECT time, code, name, code_gp, name_gp, 
                           price_now_zq, zf_30, zf_30_zq
                    FROM {table_name}
                    ORDER BY time DESC
                    LIMIT {limit}
                """
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
                if not df.empty:
                    for _, row in df.iterrows():
                        price_now = row.get('price_now_zq', 0)
                        # 买入价格 = 价格保留1位小数 + 0.1
                        # 卖出价格 = 买入价格 + 0.4
                        if price_now:
                            price_1decimal = round(price_now, 1)
                            buy_price = round(price_1decimal + 0.1, 2)
                            sell_price = round(buy_price + 0.4, 2)
                        else:
                            buy_price = None
                            sell_price = None
                        result.append({
                            'time': str(row.get('time', '')),
                            'code': str(row.get('code', '')).zfill(6) if row.get('code') else '',
                            'name': str(row.get('name', '')),
                            'code_gp': str(row.get('code_gp', '')).zfill(6) if row.get('code_gp') else '',
                            'name_gp': str(row.get('name_gp', '')),
                            'price_now_zq': price_now,
                            'buy_price': buy_price,
                            'sell_price': sell_price,
                            'zf_30': row.get('zf_30', None),
                            'zf_30_zq': row.get('zf_30_zq', None),
                        })
                    print(f"从 MySQL 获取 combine 数据: {len(result)} 条")
        except Exception as e:
            print(f"查询 combine 表失败: {e}")
        
        return result

    def get_chart_data(self, bond_code: str, stock_code: str, 
                       date: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取债券和正股的分时图数据（从 MySQL 查询）
        
        Args:
            bond_code: 债券代码
            stock_code: 正股代码（6位数字）
            date: 日期 YYYYMMDD，默认今天
        
        Returns:
            {
                'bond': [{'time': '09:30:00', 'price': 120.5, 'change_pct': 0.5, ...}, ...],
                'stock': [{'time': '09:30:00', 'price': 15.2, 'change_pct': 1.2, ...}, ...]
            }
        """
        if date is None:
            date = self.get_latest_date()
        
        bond_code = str(bond_code).zfill(6)
        stock_code = str(stock_code).zfill(6)
        
        result = {'bond': [], 'stock': []}
        
        # 查询债券分时数据
        try:
            bond_table = f"monitor_zq_sssj_{date}"
            query = f"""
                SELECT time, bond_code AS code, bond_name AS name,
                       price, change_pct, volume, amount
                FROM {bond_table}
                WHERE bond_code = '{bond_code}'
                ORDER BY time ASC
            """
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
                if not df.empty:
                    for _, row in df.iterrows():
                        result['bond'].append({
                            'time': str(row.get('time', '')),
                            'name': str(row.get('name', '')),
                            'price': float(row['price']) if row.get('price') is not None else None,
                            'change_pct': float(row['change_pct']) if row.get('change_pct') is not None else None,
                            'volume': float(row['volume']) if row.get('volume') is not None else None,
                            'amount': float(row['amount']) if row.get('amount') is not None else None,
                        })
                    print(f"从 MySQL 获取债券 {bond_code} 分时数据: {len(result['bond'])} 条")
        except Exception as e:
            print(f"查询债券分时数据失败: {e}")
        
        # 查询正股分时数据
        try:
            stock_table = f"monitor_gp_sssj_{date}"
            query = f"""
                SELECT time, stock_code AS code, short_name AS name,
                       price, change_pct, volume, amount
                FROM {stock_table}
                WHERE stock_code = '{stock_code}'
                ORDER BY time ASC
            """
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
                if not df.empty:
                    for _, row in df.iterrows():
                        result['stock'].append({
                            'time': str(row.get('time', '')),
                            'name': str(row.get('name', '')),
                            'price': float(row['price']) if row.get('price') is not None else None,
                            'change_pct': float(row['change_pct']) if row.get('change_pct') is not None else None,
                            'volume': float(row['volume']) if row.get('volume') is not None else None,
                            'amount': float(row['amount']) if row.get('amount') is not None else None,
                        })
                    print(f"从 MySQL 获取正股 {stock_code} 分时数据: {len(result['stock'])} 条")
        except Exception as e:
            print(f"查询正股分时数据失败: {e}")
        
        return result
