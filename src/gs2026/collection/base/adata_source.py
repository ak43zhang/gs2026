"""
ADATA 数据源适配器
用于替代 Baostock 获取股票日数据
"""
import time
import pandas as pd
from typing import Optional, List
from loguru import logger


class ADataSource:
    """ADATA数据源 - 股票日数据获取"""
    
    def __init__(self, request_delay: float = 0.05):
        """
        初始化
        
        Args:
            request_delay: 请求间隔(秒)
        """
        self.request_delay = request_delay
        self._import_adata()
    
    def _import_adata(self):
        """延迟导入adata，处理未安装的情况"""
        try:
            import adata
            self.adata = adata
            self.available = True
        except ImportError:
            logger.warning("ADATA未安装，请执行: pip install adata")
            self.available = False
            self.adata = None
    
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
        if not self.available:
            logger.error("ADATA未安装，无法获取数据")
            return None
        
        try:
            # 调用ADATA接口
            df = self.adata.stock.get_market(
                stock_code=stock_code,
                start_date=start_date,
                end_date=end_date
            )
            
            if df is None or df.empty:
                logger.warning(f"ADATA: {stock_code} 无数据")
                return None
            
            # 数据转换
            result = self._transform_data(df, stock_code)
            
            # 请求间隔
            time.sleep(self.request_delay)
            
            return result
            
        except Exception as e:
            logger.error(f"ADATA获取 {stock_code} 失败: {e}")
            return None
    
    def _transform_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        转换数据格式以匹配目标表结构
        
        Args:
            df: ADATA原始数据
            stock_code: 股票代码
        
        Returns:
            转换后的DataFrame
        """
        # 复制DataFrame
        df = df.copy()
        
        # 确保stock_code
        df['stock_code'] = stock_code
        
        # 字段映射（ADATA字段可能已匹配）
        column_mapping = {
            'trade_date': 'trade_date',
            'open': 'open',
            'close': 'close',
            'high': 'high',
            'low': 'low',
            'volume': 'volume',
            'amount': 'amount',
            'change': 'change',
            'change_pct': 'change_pct',
            'turnover_ratio': 'turnover_ratio',
        }
        
        # 重命名（如果字段名不同）
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns and old_col != new_col:
                df[new_col] = df[old_col]
        
        # 转换trade_date格式
        df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime('%Y-%m-%d')
        
        # 添加trade_time
        df['trade_time'] = df['trade_date'] + ' 00:00:00'
        
        # 计算pre_close（如果没有）
        if 'pre_close' not in df.columns:
            df['pre_close'] = df['close'] - df['change']
        
        # 数值类型转换
        numeric_cols = ['open', 'close', 'high', 'low', 'volume', 'amount',
                       'change_pct', 'change', 'turnover_ratio', 'pre_close']
        
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 价格字段保留2位小数
        price_cols = ['open', 'close', 'high', 'low', 'change', 'pre_close']
        for col in price_cols:
            if col in df.columns:
                df[col] = df[col].round(2)
        
        # 百分比字段
        if 'change_pct' in df.columns:
            df['change_pct'] = df['change_pct'].round(2)
        
        if 'turnover_ratio' in df.columns:
            df['turnover_ratio'] = df['turnover_ratio'].round(2)
        
        # 金额字段
        if 'amount' in df.columns:
            df['amount'] = df['amount'].round(2)
        
        # 选择目标字段
        target_cols = ['stock_code', 'trade_time', 'trade_date', 'open', 'close',
                      'high', 'low', 'volume', 'amount', 'change_pct', 'change',
                      'turnover_ratio', 'pre_close']
        
        existing_cols = [col for col in target_cols if col in df.columns]
        return df[existing_cols].copy()
    
    def get_all_stocks(self) -> List[str]:
        """
        获取所有A股代码列表
        
        Returns:
            股票代码列表
        """
        if not self.available:
            logger.error("ADATA未安装")
            return []
        
        try:
            df = self.adata.stock.all_stock()
            codes = df['stock_code'].tolist()
            logger.info(f"获取到 {len(codes)} 只股票")
            return codes
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
            return []


if __name__ == "__main__":
    # 测试
    source = ADataSource()
    
    if source.available:
        print("测试单只股票: 000001")
        df = source.get_stock_data("000001", "2026-03-27", "2026-03-27")
        if df is not None:
            print(f"获取到 {len(df)} 条数据")
            print(df.head())
    else:
        print("ADATA未安装，跳过测试")
