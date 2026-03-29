"""
股票日数据采集统一入口
支持多数据源: akshare, adata
用于替代 baostock_collection.py
"""
import time
import warnings
from typing import Optional, Literal, List
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning
from loguru import logger

from gs2026.utils import mysql_util, config_util, string_enum
from gs2026.utils.pandas_display_config import set_pandas_display_options
from gs2026.collection.base import akshare_source

warnings.filterwarnings("ignore", category=SAWarning)
set_pandas_display_options()

DataSource = Literal['akshare', 'adata']


class StockDailyCollector:
    """
    股票日数据采集器
    
    支持多数据源，批量插入，并发采集
    """
    
    def __init__(self, data_source: DataSource = 'akshare', request_delay: float = 0.1):
        """
        初始化采集器
        
        Args:
            data_source: 数据源 ('akshare' 或 'adata')
            request_delay: 请求间隔(秒)
        """
        self.data_source = data_source
        self.request_delay = request_delay
        self.source = self._init_source()
        
        # 数据库连接
        self.url = config_util.get_config("common.url")
        self.engine = create_engine(self.url, pool_recycle=3600, pool_pre_ping=True)
        self.mysql_tool = mysql_util.MysqlTool(self.url)
    
    def _init_source(self):
        """初始化数据源"""
        if self.data_source == 'akshare':
            return akshare_source.AKShareSource(request_delay=self.request_delay)
        elif self.data_source == 'adata':
            from gs2026.collection.base import adata_source
            return adata_source.ADataSource(request_delay=self.request_delay)
        else:
            raise ValueError(f"不支持的数据源: {self.data_source}")
    
    def collect(self, start_date: str, end_date: str, batch_size: int = 100, 
                max_workers: int = 1) -> None:
        """
        采集股票日数据
        
        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            batch_size: 批量插入大小
            max_workers: 并发线程数 (1=串行, >1=并发)
        """
        logger.info(f"=" * 60)
        logger.info(f"开始采集: 数据源={self.data_source}, 日期={start_date}~{end_date}")
        logger.info(f"配置: 批量={batch_size}, 并发={max_workers}")
        logger.info(f"=" * 60)
        
        # 获取交易日列表
        trade_dates = self._get_trade_dates(start_date, end_date)
        logger.info(f"共 {len(trade_dates)} 个交易日")
        
        for trade_date in trade_dates:
            self._collect_single_day(trade_date, batch_size, max_workers)
        
        logger.info("=" * 60)
        logger.info("采集完成")
        logger.info("=" * 60)
    
    def _get_trade_dates(self, start_date: str, end_date: str) -> List[str]:
        """
        获取交易日列表
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            交易日列表
        """
        sql = f"""
            SELECT trade_date 
            FROM data_jyrl 
            WHERE trade_date BETWEEN '{start_date}' AND '{end_date}' 
              AND trade_status = '1' 
            ORDER BY trade_date DESC
        """
        try:
            df = pd.read_sql(sql, con=self.engine)
            return df['trade_date'].tolist()
        except Exception as e:
            logger.error(f"获取交易日列表失败: {e}")
            # 降级：直接返回日期范围
            return pd.date_range(start=start_date, end=end_date, freq='D').strftime('%Y-%m-%d').tolist()
    
    def _collect_single_day(self, trade_date: str, batch_size: int, max_workers: int) -> None:
        """
        采集单日数据
        
        Args:
            trade_date: 交易日期
            batch_size: 批量大小
            max_workers: 并发数
        """
        table_name = f'data_gpsj_day_{trade_date.replace("-", "")}'
        
        logger.info(f"\n处理日期: {trade_date}, 表名: {table_name}")
        
        # 1. 检查并清理旧表
        if self.mysql_tool.check_table_exists(table_name):
            logger.info(f"删除旧表: {table_name}")
            self.mysql_tool.drop_mysql_table(table_name)
        
        # 2. 获取股票代码列表
        stock_codes = self._get_stock_codes()
        logger.info(f"股票数量: {len(stock_codes)}")
        
        # 3. 采集数据
        if max_workers > 1:
            # 并发采集
            self._collect_concurrent(stock_codes, trade_date, table_name, batch_size, max_workers)
        else:
            # 串行采集
            self._collect_serial(stock_codes, trade_date, table_name, batch_size)
    
    def _get_stock_codes(self) -> List[str]:
        """获取股票代码列表"""
        try:
            # 优先从数据源获取
            codes = self.source.get_all_stocks()
            if codes:
                return codes
        except Exception as e:
            logger.warning(f"从数据源获取股票列表失败: {e}")
        
        # 降级：从数据库获取
        try:
            sql = string_enum.AG_STOCK_SQL5
            df = pd.read_sql(sql, con=self.engine)
            return df.iloc[:, 0].tolist()
        except Exception as e:
            logger.error(f"从数据库获取股票列表失败: {e}")
            return []
    
    def _collect_serial(self, stock_codes: List[str], trade_date: str, 
                       table_name: str, batch_size: int) -> None:
        """
        串行采集
        
        Args:
            stock_codes: 股票代码列表
            trade_date: 交易日期
            table_name: 目标表名
            batch_size: 批量大小
        """
        all_data = []
        success_count = 0
        fail_count = 0
        
        for i, code in enumerate(stock_codes):
            # 每100只记录进度
            if (i + 1) % 100 == 0:
                logger.info(f"进度: {i+1}/{len(stock_codes)}, 成功={success_count}, 失败={fail_count}")
            
            # 获取数据
            df = self.source.get_stock_data(code, trade_date, trade_date)
            
            if df is not None and not df.empty:
                all_data.append(df)
                success_count += 1
                
                # 批量插入
                if len(all_data) >= batch_size:
                    self._batch_insert(all_data, table_name)
                    all_data = []
            else:
                fail_count += 1
        
        # 插入剩余数据
        if all_data:
            self._batch_insert(all_data, table_name)
        
        logger.info(f"完成: 成功={success_count}, 失败={fail_count}")
    
    def _collect_concurrent(self, stock_codes: List[str], trade_date: str,
                           table_name: str, batch_size: int, max_workers: int) -> None:
        """
        并发采集
        
        Args:
            stock_codes: 股票代码列表
            trade_date: 交易日期
            table_name: 目标表名
            batch_size: 批量大小
            max_workers: 并发数
        """
        all_data = []
        success_count = 0
        fail_count = 0
        processed = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_code = {
                executor.submit(self.source.get_stock_data, code, trade_date, trade_date): code
                for code in stock_codes
            }
            
            # 处理结果
            for future in as_completed(future_to_code):
                code = future_to_code[future]
                processed += 1
                
                # 进度记录
                if processed % 100 == 0:
                    logger.info(f"进度: {processed}/{len(stock_codes)}, 成功={success_count}, 失败={fail_count}")
                
                try:
                    df = future.result()
                    if df is not None and not df.empty:
                        all_data.append(df)
                        success_count += 1
                        
                        # 批量插入
                        if len(all_data) >= batch_size:
                            self._batch_insert(all_data, table_name)
                            all_data = []
                    else:
                        fail_count += 1
                except Exception as e:
                    logger.error(f"处理 {code} 失败: {e}")
                    fail_count += 1
        
        # 插入剩余数据
        if all_data:
            self._batch_insert(all_data, table_name)
        
        logger.info(f"完成: 成功={success_count}, 失败={fail_count}")
    
    def _batch_insert(self, dataframes: List[pd.DataFrame], table_name: str) -> None:
        """
        批量插入数据
        
        Args:
            dataframes: DataFrame列表
            table_name: 目标表名
        """
        if not dataframes:
            return
        
        try:
            # 合并DataFrame
            combined = pd.concat(dataframes, ignore_index=True)
            
            # 批量插入
            with self.engine.begin() as conn:
                combined.to_sql(
                    name=table_name,
                    con=conn,
                    if_exists='append',
                    index=False,
                    method='multi',
                    chunksize=1000
                )
            
            logger.info(f"批量插入: {len(combined)} 条到 {table_name}")
            
        except Exception as e:
            logger.error(f"批量插入失败: {e}")
            # 降级：逐条插入
            for df in dataframes:
                try:
                    with self.engine.begin() as conn:
                        df.to_sql(name=table_name, con=conn, if_exists='append', index=False)
                except Exception as e2:
                    logger.error(f"单条插入失败: {e2}")


def collect_stock_daily(start_date: str, end_date: str, 
                        data_source: DataSource = 'akshare',
                        batch_size: int = 100,
                        max_workers: int = 1) -> None:
    """
    采集股票日数据（便捷函数）
    
    Args:
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        data_source: 数据源
        batch_size: 批量大小
        max_workers: 并发数
    """
    collector = StockDailyCollector(data_source=data_source)
    collector.collect(start_date, end_date, batch_size, max_workers)


if __name__ == "__main__":
    import sys
    
    # 命令行参数
    if len(sys.argv) >= 3:
        start = sys.argv[1]
        end = sys.argv[2]
        source = sys.argv[3] if len(sys.argv) > 3 else 'akshare'
    else:
        # 从配置读取
        start = config_util.get_config('exe.history.baostock_collection.start_time', '2026-03-25')
        end = config_util.get_config('exe.history.baostock_collection.end_time', '2026-03-30')
        source = 'akshare'
    
    # 执行采集
    start_time = time.time()
    collect_stock_daily(start, end, data_source=source, batch_size=100, max_workers=1)
    elapsed = time.time() - start_time
    
    logger.info(f"总耗时: {elapsed:.1f} 秒")
