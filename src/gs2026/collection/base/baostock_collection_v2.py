"""
股票日数据收集 - 并发优化版本 (v2)

优化点:
1. 使用 ThreadPoolExecutor 并发获取股票数据
2. 批量写入数据库，减少事务开销
3. 自动重试机制，提高成功率
4. 实时进度显示
5. 失败统计和报告

作者: AI Assistant
版本: 2.0
日期: 2026-04-17
"""
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional, List, Dict

import baostock as bs
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning
from loguru import logger
from tqdm import tqdm

from gs2026.utils import mysql_util, config_util, string_enum
from gs2026.utils.pandas_display_config import set_pandas_display_options

warnings.filterwarnings("ignore", category=SAWarning)
set_pandas_display_options()

# 配置
url = config_util.get_config("common.url")
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True, pool_size=20, max_overflow=30)
mysql_tool = mysql_util.get_mysql_tool(url)


@dataclass
class FetchResult:
    """股票采集结果"""
    stock_code: str
    success: bool
    data: Optional[pd.DataFrame] = None
    error: Optional[str] = None
    retry_count: int = 0


@dataclass
class BaostockConfig:
    """采集配置"""
    max_workers: int = 1          # 并发线程数
    batch_size: int = 100          # 批量写入大小
    max_retries: int = 3           # 单只股票最大重试次数
    retry_delay: float = 1.0       # 重试间隔(秒)
    enable_progress: bool = True   # 是否显示进度条


class BaostockCollector:
    """Baostock 并发采集器"""
    
    def __init__(self, config: Optional[BaostockConfig] = None):
        self.config = config or BaostockConfig()
        self.login_status = False
        
    def login(self) -> bool:
        """登录 Baostock"""
        if not self.login_status:
            lg = bs.login()
            if lg.error_code == '0':
                self.login_status = True
                logger.info(f"Baostock 登录成功")
                return True
            else:
                logger.error(f"Baostock 登录失败: {lg.error_msg}")
                return False
        return True
    
    def logout(self):
        """登出 Baostock"""
        if self.login_status:
            bs.logout()
            self.login_status = False
            logger.info("Baostock 已登出")
    
    def fetch_single_stock(self, stock_code: str, start_date: str, end_date: str) -> FetchResult:
        """
        获取单只股票数据（带重试机制）
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            FetchResult: 采集结果
        """
        result = FetchResult(stock_code=stock_code, success=False)
        
        # 根据股票代码确定市场前缀
        market = "sh." if stock_code.startswith(("6", "9")) else "sz."
        full_code = market + stock_code
        
        for attempt in range(self.config.max_retries):
            try:
                # 获取单只股票历史K线（后复权）
                rs = bs.query_history_k_data_plus(
                    code=full_code,
                    fields="code,date,open,close,high,low,volume,amount,pctChg,turn,preclose",
                    start_date=start_date,
                    end_date=end_date,
                    frequency="d",
                    adjustflag="3"
                )
                
                if rs.error_code != '0':
                    result.error = f"API错误: {rs.error_msg}"
                    result.retry_count = attempt + 1
                    if attempt < self.config.max_retries - 1:
                        time.sleep(self.config.retry_delay * (attempt + 1))
                    continue
                
                # 转换为DataFrame
                data_list = []
                while rs.next():
                    data_list.append(rs.get_row_data())
                
                if not data_list:
                    result.error = "无数据返回"
                    result.retry_count = attempt + 1
                    if attempt < self.config.max_retries - 1:
                        time.sleep(self.config.retry_delay)
                    continue
                
                df = pd.DataFrame(data_list, columns=rs.fields)
                
                # 数据清洗和转换
                df["stock_code"] = df['code'].apply(lambda x: f'{x.split(".")[1]}')
                df["trade_time"] = df['date'].apply(lambda x: f'{x} 00:00:00')
                df['trade_date'] = df['date']
                df['open'] = pd.to_numeric(df['open'], errors='coerce').round(2)
                df['close'] = pd.to_numeric(df['close'], errors='coerce').round(2)
                df['high'] = pd.to_numeric(df['high'], errors='coerce').round(2)
                df['low'] = pd.to_numeric(df['low'], errors='coerce').round(2)
                df['volume'] = (pd.to_numeric(df['volume'], errors='coerce').fillna(0) // 100) * 100
                df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0).round(2)
                df['change_pct'] = pd.to_numeric(df['pctChg'], errors='coerce').fillna(0).round(2)
                df['change'] = (df['close'] - df['preclose'].astype(float)).round(2)
                df['turnover_ratio'] = pd.to_numeric(df['turn'], errors='coerce').fillna(0).round(2)
                df['pre_close'] = pd.to_numeric(df['preclose'], errors='coerce').round(2)
                
                result_df = df[["stock_code", "trade_time", 'trade_date', 'open', 'close', 'high', 'low',
                               'volume', 'amount', 'change_pct', 'change', 'turnover_ratio', 'pre_close']]
                
                result.success = True
                result.data = result_df
                return result
                
            except Exception as e:
                result.error = str(e)
                result.retry_count = attempt + 1
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay * (attempt + 1))
        
        return result
    
    def fetch_stocks_concurrent(self, stock_codes: List[str], start_date: str, end_date: str) -> List[FetchResult]:
        """
        并发获取多只股票数据
        
        Args:
            stock_codes: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            List[FetchResult]: 采集结果列表
        """
        results = []
        
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            # 提交所有任务
            future_to_code = {
                executor.submit(self.fetch_single_stock, code, start_date, end_date): code 
                for code in stock_codes
            }
            
            # 使用进度条
            iterator = as_completed(future_to_code)
            if self.config.enable_progress:
                iterator = tqdm(iterator, total=len(stock_codes), desc="采集股票数据")
            
            for future in iterator:
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    code = future_to_code[future]
                    logger.error(f"股票 {code} 采集异常: {e}")
                    results.append(FetchResult(stock_code=code, success=False, error=str(e)))
        
        return results
    
    def batch_insert_to_db(self, results: List[FetchResult], table_name: str) -> Dict[str, int]:
        """
        批量写入数据库
        
        Args:
            results: 采集结果列表
            table_name: 表名
            
        Returns:
            Dict[str, int]: 统计信息
        """
        stats = {"success": 0, "failed": 0, "total_rows": 0}
        
        # 过滤成功且有数据的
        success_results = [r for r in results if r.success and r.data is not None and not r.data.empty]
        failed_codes = [r.stock_code for r in results if not r.success]
        
        if not success_results:
            logger.warning("没有成功采集的数据需要写入")
            stats["failed"] = len(failed_codes)
            return stats
        
        # 合并所有DataFrame
        all_data = pd.concat([r.data for r in success_results], ignore_index=True)
        stats["total_rows"] = len(all_data)
        stats["success"] = len(success_results)
        stats["failed"] = len(failed_codes)
        
        # 批量写入
        try:
            with engine.begin() as conn:
                all_data.to_sql(name=table_name, con=conn, if_exists='append', index=False)
            logger.info(f"表 {table_name} 写入完成: {stats['success']} 只股票, {stats['total_rows']} 条记录")
        except Exception as e:
            logger.error(f"批量写入失败: {e}")
            stats["success"] = 0
            stats["failed"] = len(results)
        
        # 记录失败的股票
        if failed_codes:
            logger.warning(f"采集失败的股票 ({len(failed_codes)} 只): {failed_codes[:10]}...")
        
        return stats


def stock_update_v2(start_date: str, end_date: str, config: Optional[BaostockConfig] = None) -> Dict[str, int]:
    """
    更新股票数据 (v2 并发版本)
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        config: 采集配置
        
    Returns:
        Dict[str, int]: 统计信息
    """
    table_name = f'data_gpsj_day_' + start_date.replace("-", "")
    
    # 如果表存在则删除
    if mysql_tool.check_table_exists(table_name):
        mysql_tool.drop_mysql_table(table_name)
        logger.info(f"已删除旧表: {table_name}")
    
    # 获取股票代码列表
    sql = string_enum.AG_STOCK_SQL5
    with engine.connect() as conn:
        code_df = pd.read_sql(sql, con=conn)
    
    stock_codes = code_df['stock_code'].tolist()
    logger.info(f"共需采集 {len(stock_codes)} 只股票")
    
    # 创建采集器
    collector = BaostockCollector(config)
    
    try:
        # 登录
        if not collector.login():
            return {"success": 0, "failed": len(stock_codes), "total_rows": 0}
        
        # 并发采集
        logger.info(f"开始并发采集，线程数: {collector.config.max_workers}")
        start_time_ = time.time()
        results = collector.fetch_stocks_concurrent(stock_codes, start_date, end_date)
        fetch_time = time.time() - start_time_
        logger.info(f"采集完成，耗时: {fetch_time:.2f} 秒")
        
        # 批量写入
        stats = collector.batch_insert_to_db(results, table_name)
        
        # 详细统计
        success_count = sum(1 for r in results if r.success)
        failed_count = len(results) - success_count
        avg_retry = sum(r.retry_count for r in results) / len(results) if results else 0
        
        logger.info(f"=" * 50)
        logger.info(f"采集统计:")
        logger.info(f"  成功: {success_count} 只")
        logger.info(f"  失败: {failed_count} 只")
        logger.info(f"  总记录: {stats['total_rows']} 条")
        logger.info(f"  平均重试: {avg_retry:.2f} 次")
        logger.info(f"  采集耗时: {fetch_time:.2f} 秒")
        logger.info(f"=" * 50)
        
        return stats
        
    finally:
        collector.logout()


def all_stock_update_v2(start_date: str, end_date: str, config: Optional[BaostockConfig] = None) -> Dict[str, int]:
    """
    更新所有股票数据 (v2 并发版本)
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        config: 采集配置
        
    Returns:
        Dict[str, int]: 统计信息
    """
    table_name = f'data_gpsj_day_all' + start_date.replace("-", "")
    
    # 获取股票代码列表
    sql = string_enum.AG_STOCK_SQL3
    with engine.connect() as conn:
        code_df = pd.read_sql(sql, con=conn)
    
    stock_codes = code_df['stock_code'].tolist()
    logger.info(f"共需采集 {len(stock_codes)} 只股票(全部)")
    
    # 创建采集器
    collector = BaostockCollector(config)
    
    try:
        # 登录
        if not collector.login():
            return {"success": 0, "failed": len(stock_codes), "total_rows": 0}
        
        # 并发采集
        logger.info(f"开始并发采集，线程数: {collector.config.max_workers}")
        start_time = time.time()
        results = collector.fetch_stocks_concurrent(stock_codes, start_date, end_date)
        fetch_time = time.time() - start_time
        
        # 批量写入
        stats = collector.batch_insert_to_db(results, table_name)
        
        logger.info(f"全部股票采集完成，耗时: {fetch_time:.2f} 秒")
        return stats
        
    finally:
        collector.logout()


def get_baostock_collection_v2(start_date: str, end_date: str, config: Optional[BaostockConfig] = None) -> None:
    """
    采集Baostock数据 (v2 并发版本)
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        config: 采集配置
    """
    base_query_day_sql = f"""
        SELECT trade_date 
        FROM data_jyrl 
        WHERE trade_date BETWEEN '{start_date}' AND '{end_date}' 
        AND trade_status='1' 
        ORDER BY trade_date DESC
    """
    
    with engine.connect() as conn:
        base_query_day_df = pd.read_sql(base_query_day_sql, con=conn)
    
    base_query_days = base_query_day_df['trade_date'].tolist()
    logger.info(f"共需处理 {len(base_query_days)} 个交易日")
    
    for i, day in enumerate(base_query_days, 1):
        logger.info(f"[{i}/{len(base_query_days)}] 处理日期: {day}")
        stock_update_v2(day, day, config)
        logger.info("")


def run_performance_test():
    """性能测试：对比 v1 和 v2"""
    import random
    
    # 随机选择 100 只股票进行测试
    sql = string_enum.AG_STOCK_SQL5
    with engine.connect() as conn:
        code_df = pd.read_sql(sql, con=conn)
    
    all_codes = code_df['stock_code'].tolist()
    test_codes = random.sample(all_codes, min(100, len(all_codes)))
    
    logger.info(f"性能测试: 随机选择 {len(test_codes)} 只股票")
    
    # 测试日期
    test_date = "2026-04-01"
    
    # v2 并发测试
    config = BaostockConfig(max_workers=10, enable_progress=True)
    collector = BaostockCollector(config)
    
    if collector.login():
        start = time.time()
        results = collector.fetch_stocks_concurrent(test_codes, test_date, test_date)
        v2_time = time.time() - start
        collector.logout()
        
        success_count = sum(1 for r in results if r.success)
        logger.info(f"v2 并发采集: {v2_time:.2f} 秒, 成功 {success_count}/{len(test_codes)}")
        logger.info(f"平均每只股票: {v2_time/len(test_codes):.3f} 秒")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Baostock 数据采集工具 v2')
    parser.add_argument('--start', type=str, help='开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--workers', type=int, default=10, help='并发线程数 (默认: 10)')
    parser.add_argument('--test', action='store_true', help='运行性能测试')
    args = parser.parse_args()
    
    if args.test:
        run_performance_test()
    else:
        start = time.time()
        
        # 使用配置
        config = BaostockConfig(
            max_workers=args.workers,
            enable_progress=True
        )
        
        # 获取日期范围
        if args.start and args.end:
            start_time = args.start
            end_time = args.end
        else:
            start_time = config_util.get_config('exe.history.baostock_collection.start_time')
            end_time = config_util.get_config('exe.history.baostock_collection.end_time')
        
        logger.info(f"采集日期范围: {start_time} 至 {end_time}")
        logger.info(f"并发配置: {config.max_workers} 线程")
        
        # 执行采集
        get_baostock_collection_v2(start_time, end_time, config)
        
        execution_time = time.time() - start
        logger.info(f"总执行时间: {execution_time:.2f} 秒 ({execution_time/60:.2f} 分钟)")
