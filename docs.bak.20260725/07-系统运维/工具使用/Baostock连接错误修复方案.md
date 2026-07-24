# Baostock连接错误修复方案

> 问题: [WinError 10057] 套接字没有连接
> 时间: 2026-04-23 08:18
> 文件: `src/gs2026/collection/base/baostock_collection.py`

---

## 一、问题分析

### 1.1 错误原因

| 可能原因 | 说明 | 概率 |
|----------|------|------|
| **Baostock服务器不稳定** | 服务器端连接中断 | 高 |
| **网络波动** | 本地网络不稳定 | 中 |
| **连接未正确建立** | bs.login()后连接丢失 | 中 |
| **防火墙/代理** | 网络策略阻止连接 | 低 |

### 1.2 错误特征

```
[WinError 10057] 由于套接字没有连接并且(当使用一个 sendto 调用发送数据报套接字时)
没有提供地址，发送或接收数据的请求没有被接受。
```

**关键点:**
- 错误发生在 `bs.query_history_k_data_plus()` 调用时
- 说明 `bs.login()` 可能成功，但后续查询时连接断开
- 属于网络层错误，非代码逻辑错误

---

## 二、修复方案

### 方案A: 增加重试机制（推荐）

在 `get_multiple_stocks` 函数中增加重试逻辑：

```python
def get_multiple_stocks(stock_code: str, start_date: str, end_date: str, 
                        max_retries: int = 3, retry_delay: int = 5) -> Optional[pd.DataFrame]:
    """
    获取多只股票历史K线数据（带重试机制）
    """
    market = "sh." if stock_code.startswith(("6", "9")) else "sz."
    code = market + stock_code
    fields = "code,date,open,close,high,low,volume,amount,pctChg,turn,preclose"
    
    for attempt in range(max_retries):
        try:
            rs = bs.query_history_k_data_plus(
                code=code,
                fields=fields,
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="3"
            )
            
            # 检查错误码
            if rs.error_code != '0':
                logger.warning(f"查询失败: {rs.error_msg}, 错误码: {rs.error_code}")
                if attempt < max_retries - 1:
                    logger.info(f"第{attempt + 1}次重试，等待{retry_delay}秒...")
                    time.sleep(retry_delay)
                    continue
                return None
            
            # 成功获取数据，处理并返回
            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())
            
            df = pd.DataFrame(data_list, columns=rs.fields)
            if df.empty:
                logger.warning(f"stock_update>>>>>>代码：{stock_code}无值")
                return None
            
            # 数据处理...
            return result_df
            
        except Exception as e:
            logger.error(f"获取数据异常: {e}")
            if attempt < max_retries - 1:
                logger.info(f"第{attempt + 1}次重试，等待{retry_delay}秒...")
                time.sleep(retry_delay)
            else:
                logger.error(f"达到最大重试次数，放弃获取 {stock_code}")
                return None
    
    return None
```

### 方案B: 连接保活机制

在批量处理中定期重新登录：

```python
def stock_update_with_relogin(start_date: str, end_date: str, 
                              relogin_interval: int = 100) -> None:
    """
    更新股票数据（带定期重新登录）
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        relogin_interval: 每处理多少只股票重新登录一次
    """
    table_name = f'data_gpsj_day_' + start_date.replace("-", "")
    if mysql_tool.check_table_exists(table_name):
        mysql_tool.drop_mysql_table(table_name)

    sql = string_enum.AG_STOCK_SQL5
    code_df = pd.read_sql(sql, con=con)
    stock_codes = [x[0] for x in code_df.values.tolist()]

    # 初始登录
    lg = bs.login()
    logger.info(f"登录状态: {lg.error_code} - {lg.error_msg}")
    
    if lg.error_code != '0':
        logger.error("登录失败，退出")
        return

    try:
        for idx, stock_code in enumerate(stock_codes):
            # 定期重新登录
            if idx > 0 and idx % relogin_interval == 0:
                logger.info(f"已处理{idx}只股票，重新登录...")
                bs.logout()
                time.sleep(2)
                lg = bs.login()
                if lg.error_code != '0':
                    logger.error("重新登录失败")
                    break
                logger.info(f"重新登录成功")
            
            logger.info(f"正在处理：{stock_code} ({idx + 1}/{len(stock_codes)})")
            df = get_multiple_stocks(stock_code, start_date, end_date)
            
            if df is None:
                logger.error(f"stock_update>>>>>>代码：{stock_code}无值")
            else:
                with engine.begin() as conn:
                    df.to_sql(name=table_name, con=conn, if_exists='append')
                    logger.info(f"表名：{table_name}、数量：{df.shape[0]}")
    
    finally:
        # 确保登出
        bs.logout()
```

### 方案C: 批量查询优化

使用baostock的批量查询接口（如果支持），减少连接次数：

```python
def get_multiple_stocks_batch(stock_codes: List[str], start_date: str, 
                              end_date: str, batch_size: int = 50) -> pd.DataFrame:
    """
    批量获取多只股票数据
    
    分批处理，每批处理完后重新登录，避免连接超时
    """
    all_data = []
    
    for i in range(0, len(stock_codes), batch_size):
        batch = stock_codes[i:i + batch_size]
        logger.info(f"处理批次 {i//batch_size + 1}/{(len(stock_codes) + batch_size - 1)//batch_size}")
        
        # 每批重新登录
        lg = bs.login()
        if lg.error_code != '0':
            logger.error(f"登录失败: {lg.error_msg}")
            continue
        
        try:
            for stock_code in batch:
                df = get_multiple_stocks(stock_code, start_date, end_date)
                if df is not None:
                    all_data.append(df)
        finally:
            bs.logout()
        
        # 批次间暂停
        if i + batch_size < len(stock_codes):
            time.sleep(3)
    
    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return pd.DataFrame()
```

---

## 三、完整修复代码

### 修改后的 `baostock_collection.py`

```python
"""
股票日数据收集 - 修复版
增加重试机制和连接保活
"""
import time
import warnings
from typing import Optional, List

import baostock as bs
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SAWarning
from loguru import logger

from gs2026.utils import mysql_util, config_util, string_enum
from gs2026.utils.pandas_display_config import set_pandas_display_options

warnings.filterwarnings("ignore", category=SAWarning)
set_pandas_display_options()

url = config_util.get_config("common.url")
engine = create_engine(url, pool_recycle=3600, pool_pre_ping=True)
con = engine.connect()
mysql_tool = mysql_util.get_mysql_tool(url)


def get_multiple_stocks(stock_code: str, start_date: str, end_date: str,
                        max_retries: int = 3, retry_delay: int = 5) -> Optional[pd.DataFrame]:
    """
    获取单只股票历史K线数据（带重试机制）
    
    Args:
        stock_code: 股票代码
        start_date: 开始日期
        end_date: 结束日期
        max_retries: 最大重试次数
        retry_delay: 重试间隔（秒）
    
    Returns:
        股票数据DataFrame或None
    """
    market = "sh." if stock_code.startswith(("6", "9")) else "sz."
    code = market + stock_code
    fields = "code,date,open,close,high,low,volume,amount,pctChg,turn,preclose"
    
    for attempt in range(max_retries):
        try:
            rs = bs.query_history_k_data_plus(
                code=code,
                fields=fields,
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="3"
            )
            
            # 检查返回错误
            if rs.error_code != '0':
                logger.warning(f"查询{stock_code}失败: {rs.error_msg} (错误码: {rs.error_code})")
                if attempt < max_retries - 1:
                    logger.info(f"第{attempt + 1}次重试，等待{retry_delay}秒...")
                    time.sleep(retry_delay)
                    continue
                return None
            
            # 读取数据
            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())
            
            df = pd.DataFrame(data_list, columns=rs.fields)
            if df.empty:
                logger.warning(f"stock_update>>>>>>代码：{stock_code}无值")
                return None
            
            # 数据处理
            df["stock_code"] = df['code'].apply(lambda x: f'{x.split(".")[1]}')
            df["trade_time"] = df['date'].apply(lambda x: f'{x + " 00:00:00"}')
            df['trade_date'] = df['date']
            df['open'] = df['open'].round(2).astype(float)
            df['close'] = df['close'].round(2).astype(float)
            df['high'] = df['high'].round(2).astype(float)
            df['low'] = df['low'].round(2).astype(float)
            df['volume'] = (df['volume'].replace(r'^\s*$', '0', regex=True).astype(float) // 100) * 100
            df['amount'] = df['amount'].replace(r'^\s*$', '0', regex=True).astype(float).round(2)
            df['change_pct'] = df['pctChg'].replace(r'^\s*$', '0', regex=True).astype(float).round(2)
            df['change'] = (df['close'].astype(float) - df['preclose'].astype(float)).astype(float).round(2)
            df['turnover_ratio'] = df['turn'].replace(r'^\s*$', '0', regex=True).astype(float).round(2)
            df['pre_close'] = df['preclose'].round(2).astype(float)
            
            result_df = df[["stock_code", "trade_time", 'trade_date', 'open', 'close', 'high', 'low',
                           'volume', 'amount', 'change_pct', 'change', 'turnover_ratio', 'pre_close']]
            return result_df
            
        except Exception as e:
            logger.error(f"获取{stock_code}数据异常: {e}")
            if attempt < max_retries - 1:
                logger.info(f"第{attempt + 1}次重试，等待{retry_delay}秒...")
                time.sleep(retry_delay)
            else:
                logger.error(f"达到最大重试次数，放弃获取 {stock_code}")
                return None
    
    return None


def stock_update(start_date: str, end_date: str, relogin_interval: int = 100) -> None:
    """
    更新股票数据（带定期重新登录）
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        relogin_interval: 每处理多少只股票重新登录一次
    """
    table_name = f'data_gpsj_day_' + start_date.replace("-", "")
    if mysql_tool.check_table_exists(table_name):
        mysql_tool.drop_mysql_table(table_name)

    sql = string_enum.AG_STOCK_SQL5
    code_df = pd.read_sql(sql, con=con)
    stock_codes = [x[0] for x in code_df.values.tolist()]

    logger.info(f"共需处理 {len(stock_codes)} 只股票")

    # 初始登录
    lg = bs.login()
    logger.info(f"登录状态: {lg.error_code} - {lg.error_msg}")
    
    if lg.error_code != '0':
        logger.error("登录失败，退出")
        return

    success_count = 0
    fail_count = 0
    
    try:
        for idx, stock_code in enumerate(stock_codes):
            # 定期重新登录
            if idx > 0 and idx % relogin_interval == 0:
                logger.info(f"已处理{idx}只股票，重新登录...")
                bs.logout()
                time.sleep(2)
                lg = bs.login()
                if lg.error_code != '0':
                    logger.error(f"重新登录失败: {lg.error_msg}")
                    break
                logger.info("重新登录成功")
            
            logger.info(f"正在处理：{stock_code} ({idx + 1}/{len(stock_codes)})")
            df = get_multiple_stocks(stock_code, start_date, end_date)
            
            if df is None:
                logger.error(f"stock_update>>>>>>代码：{stock_code}无值")
                fail_count += 1
            else:
                try:
                    with engine.begin() as conn:
                        df.to_sql(name=table_name, con=conn, if_exists='append')
                        logger.info(f"表名：{table_name}、数量：{df.shape[0]}")
                        success_count += 1
                except Exception as e:
                    logger.error(f"写入数据库失败: {e}")
                    fail_count += 1
    
    finally:
        # 确保登出
        bs.logout()
        logger.info(f"处理完成: 成功 {success_count}, 失败 {fail_count}")


def all_stock_update(start_date: str, end_date: str) -> None:
    """
    更新所有股票数据
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
    """
    table_name = f'data_gpsj_day_all' + start_date.replace("-", "")

    sql = string_enum.AG_STOCK_SQL3
    code_df = pd.read_sql(sql, con=con)
    stock_codes = [x[0] for x in code_df.values.tolist()]

    # 登录系统
    lg = bs.login()
    logger.info(f"登录状态: {lg.error_code} - {lg.error_msg}")
    
    if lg.error_code != '0':
        logger.error("登录失败，退出")
        return

    try:
        for stock_code in stock_codes:
            logger.info(f"正在处理：{stock_code}")
            df = get_multiple_stocks(stock_code, start_date, end_date)
            logger.info(f"{df.shape[0] if df is not None else 0}")
            if df is None:
                logger.error(f"stock_update>>>>>>代码：{stock_code}无值")
            else:
                try:
                    with engine.begin() as conn:
                        df.to_sql(name=table_name, con=conn, if_exists='append')
                        logger.info(f"表名：{table_name}、数量：{df.shape[0]}")
                except Exception as e:
                    logger.error(f"写入数据库失败: {e}")
    finally:
        # 登出系统
        bs.logout()


def get_baostock_collection(start_date: str, end_date: str) -> None:
    """
    采集Baostock数据
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
    """
    stock_update(start_date, end_date)


if __name__ == "__main__":
    # 测试
    get_baostock_collection("2026-04-01", "2026-04-22")
```

---

## 四、使用建议

### 4.1 立即执行

```bash
# 1. 备份原文件
copy F:\pyworkspace2026\gs2026\src\gs2026\collection\base\baostock_collection.py F:\pyworkspace2026\gs2026\src\gs2026\collection\base\baostock_collection.py.bak

# 2. 应用修复
# 使用上面的完整修复代码替换原文件

# 3. 测试运行
cd F:\pyworkspace2026\gs2026
.\.venv\Scripts\python.exe -c "from src.gs2026.collection.base.baostock_collection import get_baostock_collection; get_baostock_collection('2026-04-22', '2026-04-22')"
```

### 4.2 参数调整

| 参数 | 说明 | 默认值 | 建议值 |
|------|------|--------|--------|
| `max_retries` | 单只股票最大重试次数 | 3 | 3-5 |
| `retry_delay` | 重试间隔（秒） | 5 | 5-10 |
| `relogin_interval` | 重新登录间隔（股票数） | 100 | 50-100 |

### 4.3 网络检查

```bash
# 检查网络连接
ping www.baostock.com

# 检查DNS解析
nslookup www.baostock.com

# 检查代理设置（如有）
echo %HTTP_PROXY%
echo %HTTPS_PROXY%
```

---

## 五、备选方案

如果baostock持续不稳定，考虑：

1. **使用baostock_collection_v2.py**（并发版本）
2. **更换数据源**: 使用tushare、akshare等替代
3. **增加代理**: 配置HTTP代理访问baostock

---

**方案状态**: 待审核
**推荐**: 方案A（重试机制）+ 方案B（定期重新登录）
