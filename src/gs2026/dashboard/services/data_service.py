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


def _calculate_window_start(time_str: str) -> str:
    """
    计算15分钟区间起始时间
    
    区间划分：
    - 09:30-09:45 -> 09:30:00
    - 09:45-10:00 -> 09:45:00
    - 10:00-10:15 -> 10:00:00
    - ...以此类推
    
    Args:
        time_str: 时间字符串，格式 HH:MM:SS
        
    Returns:
        区间起始时间字符串，格式 HH:MM:SS
    """
    hour = int(time_str[:2])
    minute = int(time_str[3:5])
    # 15分钟区间：0, 15, 30, 45
    window_minute = (minute // 15) * 15
    return f"{hour:02d}:{window_minute:02d}:00"


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
        
        # 【优化】主线可转债智能刷新缓存
        self._last_combine_count = 0
        self._last_combine_data = None
    
    def _get_combine_count(self, date: str, time_str: str = None) -> int:
        """获取当前 combine 数据数量（用于智能刷新判断）"""
        table_name = f"monitor_combine_{date}"
        
        # 从 Redis 获取数量
        if self.redis_available:
            try:
                client = redis_util._get_redis_client()
                ts_list_key = f"{table_name}:timestamps"
                total_ts = client.llen(ts_list_key)
                
                if total_ts > 0:
                    # 获取所有时间戳
                    all_ts = client.lrange(ts_list_key, 0, -1)
                    count = 0
                    for ts_data in all_ts:
                        ts = ts_data.decode('utf-8') if isinstance(ts_data, bytes) else ts_data
                        if time_str and ts > time_str:
                            continue
                        key = f"{table_name}:{ts}"
                        df = redis_util.load_dataframe_by_key(key, use_compression=False)
                        if df is not None:
                            count += len(df)
                    return count
            except Exception as e:
                pass
        
        # 无法获取数量，返回 -1 表示未知
        return -1
    
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
            {'stock': {...}, 'bond': {...}, 'market_avg': [...]}
        """
        if date is None:
            date = self.get_latest_date()
        
        result = {'stock': None, 'bond': None, 'market_avg': []}
        
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
                    # 查询market_avg后返回
                    result['market_avg'] = self._query_market_avg(date)
                    return result
            except Exception as e:
                print(f"按时间查询 Redis 失败: {e}")
            
            # fallback 到 MySQL
            if use_mysql:
                result['stock'] = self._query_market_by_time('monitor_gp_apqd', time_str, date)
                result['bond'] = self._query_market_by_time('monitor_zq_apqd', time_str, date)
            result['market_avg'] = self._query_market_avg(date)
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
                
                # 如果 Redis 都有数据，查询market_avg后返回
                if result['stock'] and result['bond']:
                    result['market_avg'] = self._query_market_avg(date)
                    return result
                    
            except Exception as e:
                print(f"Redis 查询失败: {e}")
        
        # 2. 如果 use_mysql=False，直接返回（可能部分为空）
        if not use_mysql:
            print("Redis 无数据且 use_mysql=False，返回空")
            result['market_avg'] = self._query_market_avg(date)
            return result
        
        # 3. 查询 MySQL
        # 获取最新时间（从股票表）
        latest_time = self._get_latest_time('monitor_gp_apqd', date)
        
        if latest_time:
            # 查询同一时间的数据
            result['stock'] = self._query_market_by_time('monitor_gp_apqd', latest_time, date)
            result['bond'] = self._query_market_by_time('monitor_zq_apqd', latest_time, date)
        
        # 4. 查询大盘均值分时数据（用于悬浮分时图）- 无论前面从哪里获取数据，都执行
        result['market_avg'] = self._query_market_avg(date)
        
        return result
    
    def _query_market_avg(self, date: Optional[str] = None) -> List[Dict]:
        """查询大盘均值分时数据（全天）"""
        if date is None:
            date = self.get_latest_date()
        
        try:
            import time as time_module
            start_time = time_module.time()
            apqd_table = f"monitor_gp_apqd_{date}"
            query = f"""
                SELECT time, avg_change_pct as change_pct
                FROM {apqd_table}
                ORDER BY time ASC
            """
            print(f"[SQL] 查询大盘均值: {apqd_table}")
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
                elapsed = time_module.time() - start_time
                print(f"[SQL] 大盘均值查询耗时: {elapsed:.3f}s, 返回 {len(df)} 条")
                if not df.empty:
                    df['time'] = df['time'].astype(str)
                    return df[['time', 'change_pct']].to_dict('records')
                else:
                    print(f"[DATA] market_avg: 空")
                    return []
        except Exception as e:
            print(f"[ERROR] 查询大盘均值失败: {e}")
            return []
    
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
                trend_score,
                body_up,
                body_down,
                body_flat,
                body_up_down_ratio,
                market_phase,
                phase_strength,
                phase_momentum,
                avg_change_pct
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
                end_idx = limit - 1 if limit > 0 else -1  # limit=0 → 返回全量
                rank_data = redis_util._get_redis_client().zrevrange(redis_code_key, 0, end_idx, withscores=True)
                
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
                    
                    # 行业排行：从Redis补充 industry_cumulative_main_net
                    if asset_type == 'industry' and result:
                        try:
                            client = redis_util._get_redis_client()
                            table_name = self.get_table_name(config['table_prefix'], date)
                            latest_time = client.lindex(f"{table_name}:timestamps", 0)
                            if latest_time:
                                latest_time = latest_time.decode('utf-8') if isinstance(latest_time, bytes) else latest_time
                                data_json = client.get(f"{table_name}:{latest_time}")
                                if data_json:
                                    import json
                                    if isinstance(data_json, bytes):
                                        data_json = data_json.decode('utf-8')
                                    all_industries = json.loads(data_json)
                                    net_map = {str(row.get('code', '')): row.get('industry_cumulative_main_net')
                                               for row in all_industries}
                                    for item in result:
                                        item['industry_cumulative_main_net'] = net_map.get(item['code'])
                        except Exception as e:
                            print(f"补充 industry_cumulative_main_net 失败: {e}")
                    
                    # 股票/债券排行：从Redis hash获取当前区间的 window_count
                    if asset_type in ['stock', 'bond'] and result:
                        try:
                            client = redis_util._get_redis_client()
                            table_name = self.get_table_name(config['table_prefix'], date)
                            wc_data = client.hgetall(f"{table_name}:wc")
                            if wc_data:
                                wc_map = {(k.decode() if isinstance(k, bytes) else k): 
                                          int(v) for k, v in wc_data.items()}
                                for item in result:
                                    item['window_count'] = wc_map.get(item['code'], 0)
                            else:
                                for item in result:
                                    item['window_count'] = 0
                        except Exception as e:
                            print(f"补充 window_count 失败: {e}")
                            for item in result:
                                item['window_count'] = item.get('window_count', 0)
                    
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
                    {f'LIMIT {limit}' if limit > 0 else ''}
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
        
        # 【修复】只查最后一个时间点的数据，而非多个时间点的累计统计
        # 根据资产类型选择正确的字段和排序
        if asset_type == 'industry':
            query = f"""
                SELECT 
                    {config['code_col']} as code,
                    {config['name_col']} as name,
                    avg_change_pct,
                    final_score,
                    `rank`,
                    industry_cumulative_main_net
                FROM {table_name}
                WHERE `time` = (SELECT MAX(`time`) FROM {table_name})
                ORDER BY `rank` ASC
                {f'LIMIT {limit}' if limit > 0 else ''}
            """
        else:
            query = f"""
                SELECT 
                    {config['code_col']} as code,
                    {config['name_col']} as name,
                    price_now,
                    zf_30,
                    momentum,
                    amount_now,
                    total_score,
                    total_score_rank
                FROM {table_name}
                WHERE `time` = (SELECT MAX(`time`) FROM {table_name})
                ORDER BY total_score_rank ASC
                {f'LIMIT {limit}' if limit > 0 else ''}
            """
        
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
                
                if not df.empty:
                    for idx, row in df.iterrows():
                        row_data = {
                            'code': str(row['code']),
                            'name': str(row['name']),
                            'count': idx + 1,  # 排名序号（兼容前端 count 字段）
                            'type': asset_type,
                            'date': date,
                            'rank': idx + 1
                        }
                        
                        # 添加额外字段（如果有）
                        if 'price_now' in df.columns:
                            row_data['latest_price'] = row.get('price_now')
                        if 'zf_30' in df.columns:
                            row_data['zf_30'] = row.get('zf_30')
                        if 'momentum' in df.columns:
                            row_data['momentum'] = row.get('momentum')
                        if 'total_score' in df.columns:
                            row_data['total_score'] = row.get('total_score')
                        if 'final_score' in df.columns:
                            row_data['total_score'] = row.get('final_score')
                        if 'industry_cumulative_main_net' in df.columns:
                            row_data['industry_cumulative_main_net'] = row.get('industry_cumulative_main_net')
                        
                        # 区间次数（兼容代码开始）
                        if 'window_count' in df.columns:
                            try:
                                row_data['window_count'] = int(row['window_count'])
                            except (ValueError, TypeError):
                                row_data['window_count'] = 0
                        else:
                            row_data['window_count'] = 0
                        # 兼容代码结束
                        
                        result.append(row_data)
                    
                    print(f"从 MySQL 实时表获取 {asset_type} 最后时间点排行: {len(result)} 条")
                
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
        
        行业类型：Redis优先（DataFrame缓存），MySQL fallback
        股票/债券：直接查MySQL
        
        Args:
            asset_type: 资产类型，'stock' | 'bond' | 'industry'
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
        
        # ===== 行业类型：Redis优先 =====
        if asset_type == 'industry' and self.redis_available:
            try:
                import json
                client = redis_util._get_redis_client()
                timestamps = client.lrange(f"{table_name}:timestamps", 0, -1)
                if timestamps:
                    timestamps = [t.decode('utf-8') if isinstance(t, bytes) else t for t in timestamps]
                    if time_str:
                        timestamps = [t for t in timestamps if t <= time_str]
                    
                    if timestamps:
                        code_counts = {}
                        code_names = {}
                        latest_net = {}
                        
                        for ts in timestamps:
                            data_json = client.get(f"{table_name}:{ts}")
                            if not data_json:
                                continue
                            if isinstance(data_json, bytes):
                                data_json = data_json.decode('utf-8')
                            rows = json.loads(data_json)
                            for row in rows:
                                if row.get('rank', 999) <= 5:
                                    code = str(row.get('code', ''))
                                    code_counts[code] = code_counts.get(code, 0) + 1
                                    code_names[code] = row.get('name', '')
                        
                        # 从最新时间点获取 industry_cumulative_main_net
                        latest_ts = max(timestamps)
                        latest_json = client.get(f"{table_name}:{latest_ts}")
                        if latest_json:
                            if isinstance(latest_json, bytes):
                                latest_json = latest_json.decode('utf-8')
                            for row in json.loads(latest_json):
                                latest_net[str(row.get('code', ''))] = row.get('industry_cumulative_main_net')
                        
                        result = []
                        sorted_codes = sorted(code_counts.keys(), key=lambda c: code_counts[c], reverse=True)
                        if limit > 0:
                            sorted_codes = sorted_codes[:limit]
                        for idx, code in enumerate(sorted_codes):
                            result.append({
                                'code': code,
                                'name': code_names.get(code, ''),
                                'count': code_counts[code],
                                'type': asset_type,
                                'date': date,
                                'rank': idx + 1,
                                'industry_cumulative_main_net': latest_net.get(code)
                            })
                        
                        if result:
                            time_desc = f"截止{time_str}" if time_str else "全天"
                            print(f"从 Redis 获取 {asset_type} {time_desc} 排行: {len(result)} 条")
                            return result
            except Exception as e:
                print(f"Redis 行业时间排行查询失败: {e}")
        
        # ===== MySQL fallback =====
        time_filter = f"AND time <= '{time_str}'" if time_str else ""
        # 行业表存全部行业（90条/时间点），只统计rank<=5的才与Redis累计排行一致
        rank_filter = "AND `rank` <= 5" if asset_type == 'industry' else ""
        
        query = f"""
            SELECT {config['code_col']} AS code, 
                   {config['name_col']} AS name,
                   COUNT(*) AS count
            FROM {table_name}
            WHERE 1=1 {time_filter} {rank_filter}
            GROUP BY {config['code_col']}, {config['name_col']}
            ORDER BY count DESC
            {f'LIMIT {limit}' if limit > 0 else ''}
        """
        
        result = []
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
                if not df.empty:
                    # 行业类型补充 industry_cumulative_main_net
                    net_map = {}
                    if asset_type == 'industry':
                        try:
                            max_time_filter = f"AND `time` <= '{time_str}'" if time_str else ""
                            # 为每个行业取截止时间点的最新主力净额（不限于rank<=5）
                            net_query = f"""
                                SELECT t1.{config['code_col']} as code, t1.industry_cumulative_main_net
                                FROM {table_name} t1
                                INNER JOIN (
                                    SELECT {config['code_col']}, MAX(`time`) as max_time
                                    FROM {table_name}
                                    WHERE 1=1 {max_time_filter}
                                    GROUP BY {config['code_col']}
                                ) t2 ON t1.{config['code_col']} = t2.{config['code_col']} AND t1.`time` = t2.max_time
                            """
                            net_df = pd.read_sql(net_query, conn)
                            net_map = dict(zip(net_df['code'].astype(str), net_df['industry_cumulative_main_net']))
                        except Exception:
                            pass
                    
                    # 【修复】为股票/债券查询window_count（按时间区间统计）
                    window_count_map = {}
                    if asset_type in ['stock', 'bond'] and time_str:
                        try:
                            codes = df['code'].astype(str).tolist()
                            codes_str = "','".join(codes)
                            # 计算当前时间所在的15分钟区间起始时间
                            window_start = _calculate_window_start(time_str)
                            # 查询该区间内每个code的最大window_count（即当前区间的累计次数）
                            wc_query = f"""
                                SELECT code, MAX(window_count) as window_count
                                FROM {table_name}
                                WHERE code IN ('{codes_str}') 
                                AND time >= '{window_start}' AND time <= '{time_str}'
                                GROUP BY code
                            """
                            wc_df = pd.read_sql(wc_query, conn)
                            window_count_map = dict(zip(wc_df['code'].astype(str), 
                                                        wc_df['window_count'].fillna(0).astype(int)))
                        except Exception:
                            pass
                    
                    for idx, row in df.iterrows():
                        item = {
                            'code': str(row['code']),
                            'name': str(row['name']),
                            'count': int(row['count']),
                            'type': asset_type,
                            'date': date,
                            'rank': idx + 1
                        }
                        if asset_type == 'industry':
                            item['industry_cumulative_main_net'] = net_map.get(str(row['code']))
                        # 【新增】为股票/债券添加window_count
                        if asset_type in ['stock', 'bond']:
                            item['window_count'] = window_count_map.get(str(row['code']), 0)
                        result.append(item)
                    time_desc = f"截止{time_str}" if time_str else "全天"
                    print(f"从 MySQL 获取 {asset_type} {time_desc} 排行: {len(result)} 条")
        except Exception as e:
            print(f"查询 {asset_type} 时间排行失败: {e}")
        
        return result

    def get_combine_ranking(self, limit: int = 50, date: Optional[str] = None, time_str: Optional[str] = None, check_change: bool = False) -> List[Dict[str, Any]]:
        """
        获取股债联动信号数据（monitor_combine 表）
        
        优先从 Redis 获取最新数据，如果没有则查 MySQL。
        返回按 time 倒序排列的记录。
        
        【优化】支持智能刷新：通过 check_change=True 只获取变化后的数据
        
        Args:
            limit: 返回条数
            date: 日期字符串 YYYYMMDD，默认今天
            time_str: 时间过滤，只返回该时间之前的数据（包含该时间）
            check_change: 是否检查数据变化，True=数量未变时返回缓存
        
        Returns:
            信号数据列表
        """
        if date is None:
            date = self.get_latest_date()
        
        # 【优化】智能刷新：检查数量是否变化
        if check_change:
            current_count = self._get_combine_count(date, time_str)
            if current_count == self._last_combine_count and self._last_combine_data is not None:
                # 数量未变，返回缓存数据
                return self._last_combine_data
        
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
        
        # 【优化】更新缓存
        if check_change:
            self._last_combine_count = self._get_combine_count(date, time_str)
            self._last_combine_data = result
        
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
        
        bond_code = str(bond_code).zfill(6) if bond_code and bond_code != 'none' else ''
        stock_code = str(stock_code).zfill(6) if stock_code and stock_code != 'none' else ''
        
        # 如果没有正股代码但有债券代码，从映射表反查
        if not stock_code and bond_code:
            try:
                from gs2026.utils.stock_bond_mapping_cache import get_cache
                cache = get_cache()
                all_mapping = cache.get_all_mapping()
                if all_mapping:
                    for k, v in all_mapping.items():
                        if isinstance(v, dict) and v.get('bond_code') == bond_code:
                            stock_code = v.get('stock_code', '')
                            break
                if stock_code:
                    print(f"反查正股: {bond_code} -> {stock_code}")
            except Exception as e:
                print(f"反查正股代码失败: {e}")
        
        result = {'bond': [], 'stock': [], 'market_avg': [], 'industry_avg': [], 'industry_name': ''}
        
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
                    df['time'] = df['time'].astype(str)
                    df['name'] = df['name'].astype(str)
                    result['bond'] = df[['time', 'name', 'price', 'change_pct', 'volume', 'amount']].to_dict('records')
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
                    df['time'] = df['time'].astype(str)
                    df['name'] = df['name'].astype(str)
                    result['stock'] = df[['time', 'name', 'price', 'change_pct', 'volume', 'amount']].to_dict('records')
                    print(f"从 MySQL 获取正股 {stock_code} 分时数据: {len(result['stock'])} 条")
        except Exception as e:
            print(f"查询正股分时数据失败: {e}")
        
        # 查询大盘均值分时（从 monitor_gp_apqd 表）
        try:
            apqd_table = f"monitor_gp_apqd_{date}"
            query = f"""
                SELECT time, avg_change_pct as change_pct
                FROM {apqd_table}
                ORDER BY time ASC
            """
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
                if not df.empty:
                    df['time'] = df['time'].astype(str)
                    result['market_avg'] = df[['time', 'change_pct']].to_dict('records')
        except Exception as e:
            print(f"查询大盘均值失败: {e}")
        
        # 查询行业均值分时（从 monitor_hy_sssj 表）
        # 方案: 从 cache_stock_industry_concept_bond 获取行业名称，
        # 然后从 monitor_hy_sssj 查询该行业的涨跌幅分时数据
        try:
            if stock_code:
                # 1. 从缓存表获取行业名称
                industry_query = f"""
                    SELECT industry_names 
                    FROM cache_stock_industry_concept_bond 
                    WHERE stock_code = '{stock_code}'
                    LIMIT 1
                """
                with self.engine.connect() as conn:
                    ind_df = pd.read_sql(industry_query, conn)
                    if not ind_df.empty and ind_df.iloc[0]['industry_names']:
                        import json
                        industry_names = json.loads(ind_df.iloc[0]['industry_names'])
                        if industry_names and len(industry_names) > 0:
                            bk_name = industry_names[0]  # 取第一个行业
                            result['industry_name'] = bk_name
                            
                            # 2. 从 monitor_hy_sssj 查询该行业的分时数据
                            hy_table = f"monitor_hy_sssj_{date}"
                            hy_query = f"""
                                SELECT time, 涨跌幅 as change_pct
                                FROM {hy_table}
                                WHERE 板块 = '{bk_name}'
                                ORDER BY time ASC
                            """
                            hy_df = pd.read_sql(hy_query, conn)
                            if not hy_df.empty:
                                hy_df['time'] = hy_df['time'].astype(str)
                                result['industry_avg'] = hy_df[['time', 'change_pct']].to_dict('records')
        except Exception as e:
            print(f"查询行业均值失败: {e}")
        
        return result
