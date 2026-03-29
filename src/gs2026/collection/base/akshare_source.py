"""
AKShare 数据源适配器
用于替代 Baostock 获取股票日数据
"""
import time
import akshare as ak
import pandas as pd
from typing import Optional, List
from loguru import logger


class AKShareSource:
    """AKShare数据源 - 股票日数据获取"""
    
    # 字段映射: AKShare字段 -> 目标字段
    FIELD_MAPPING = {
        '日期': 'trade_date',
        '开盘': 'open',
        '收盘': 'close',
        '最高': 'high',
        '最低': 'low',
        '成交量': 'volume',
        '成交额': 'amount',
        '振幅': 'amplitude',
        '涨跌幅': 'change_pct',
        '涨跌额': 'change',
        '换手率': 'turnover_ratio',
    }
    
    def __init__(self, request_delay: float = 0.1):
        """
        初始化
        
        Args:
            request_delay: 请求间隔(秒)，防止反爬
        """
        self.request_delay = request_delay
    
    def get_stock_data(self, stock_code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """
        获取单只股票历史数据
        
        Args:
            stock_code: 股票代码 (如: 600000, 000001)
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
        
        Returns:
            DataFrame或None
        """
        try:
            # 转换日期格式 (YYYY-MM-DD -> YYYYMMDD)
            start = start_date.replace("-", "")
            end = end_date.replace("-", "")
            
            # 调用AKShare接口
            df = ak.stock_zh_a_hist(
                symbol=stock_code,
                period="daily",
                start_date=start,
                end_date=end,
                adjust="qfq"  # 前复权
            )
            
            if df is None or df.empty:
                logger.warning(f"AKShare: {stock_code} 无数据")
                return None
            
            # 数据转换
            result = self._transform_data(df, stock_code)
            
            # 请求间隔
            time.sleep(self.request_delay)
            
            return result
            
        except Exception as e:
            logger.error(f"AKShare获取 {stock_code} 失败: {e}")
            return None
    
    def _transform_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        转换数据格式以匹配目标表结构
        
        Args:
            df: AKShare原始数据
            stock_code: 股票代码
        
        Returns:
            转换后的DataFrame
        """
        # 复制DataFrame避免修改原数据
        df = df.copy()
        
        # 重命名字段
        df = df.rename(columns=self.FIELD_MAPPING)
        
        # 添加stock_code字段
        df['stock_code'] = stock_code
        
        # 转换trade_date格式 (YYYYMMDD -> YYYY-MM-DD)
        df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y-%m-%d')
        
        # 添加trade_time字段
        df['trade_time'] = df['trade_date'] + ' 00:00:00'
        
        # 计算pre_close（昨收 = 收盘 - 涨跌额）
        df['pre_close'] = df['close'] - df['change']
        
        # 数值类型转换和精度处理
        numeric_cols = ['open', 'close', 'high', 'low', 'volume', 'amount', 
                       'change_pct', 'change', 'turnover_ratio', 'pre_close']
        
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 成交量转换：AKShare返回的是"手"，转换为"股"（1手=100股）
        if 'volume' in df.columns:
            df['volume'] = (df['volume'] * 100).astype(float)
        
        # 价格字段保留2位小数
        price_cols = ['open', 'close', 'high', 'low', 'change', 'pre_close']
        for col in price_cols:
            if col in df.columns:
                df[col] = df[col].round(2)
        
        # 百分比字段处理
        if 'change_pct' in df.columns:
            df['change_pct'] = df['change_pct'].round(2)
        
        if 'turnover_ratio' in df.columns:
            df['turnover_ratio'] = df['turnover_ratio'].round(2)
        
        # 金额字段保留2位小数
        if 'amount' in df.columns:
            df['amount'] = df['amount'].round(2)
        
        # 选择目标字段（按目标表顺序）
        target_cols = ['stock_code', 'trade_time', 'trade_date', 'open', 'close', 
                      'high', 'low', 'volume', 'amount', 'change_pct', 'change',
                      'turnover_ratio', 'pre_close']
        
        # 只保留存在的字段
        existing_cols = [col for col in target_cols if col in df.columns]
        result_df = df[existing_cols].copy()
        
        return result_df
    
    def get_all_stocks(self) -> List[str]:
        """
        获取所有A股代码列表
        
        Returns:
            股票代码列表
        """
        try:
            df = ak.stock_zh_a_spot_em()
            codes = df['代码'].tolist()
            logger.info(f"获取到 {len(codes)} 只股票")
            return codes
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
            return []
    
    def get_stock_name(self, stock_code: str) -> str:
        """
        获取股票名称
        
        Args:
            stock_code: 股票代码
        
        Returns:
            股票名称
        """
        try:
            df = ak.stock_zh_a_spot_em()
            name = df[df['代码'] == stock_code]['名称'].values
            return name[0] if len(name) > 0 else ""
        except Exception as e:
            logger.error(f"获取股票名称失败: {e}")
            return ""


if __name__ == "__main__":
    # 测试
    source = AKShareSource()
    
    # 测试单只股票
    print("测试单只股票: 000001")
    df = source.get_stock_data("000001", "2026-03-25", "2026-03-30")
    if df is not None:
        print(f"获取到 {len(df)} 条数据")
        print(df.head())
    
    # 测试股票列表
    print("\n测试获取股票列表(前10只):")
    codes = source.get_all_stocks()
    print(codes[:10])
