# Baostock替代方案 - 网络问题排查与备用方案

> 日期: 2026-04-23
> 问题: akshare和adata都因网络问题无法获取数据

---

## 问题排查结果

### 1. AKShare 问题

**症状**: `ConnectionError: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))`

**排查**:
- ✅ socket连接 `quote.eastmoney.com:80` 成功
- ✅ requests访问 `push2.eastmoney.com` 成功 (status=200)
- ❌ akshare的 `stock_zh_a_hist` API 失败
- ❌ 直接访问kline API URL 也失败

**结论**: 不是网络不通，而是特定API被限制或需要特殊处理（可能是User-Agent、Cookie、或频率限制）

### 2. AData 问题

**症状**: API返回空数据

**排查**:
- ✅ adata已安装 (v2.9.0)
- ✅ 正确API: `adata.stock.market.get_market()`
- ❌ 返回空DataFrame (rows=0)

**结论**: API调用正确但数据源无返回，可能是日期格式或数据源问题

---

## 备用方案

### 方案A: 修复AKShare（推荐尝试）

修改 `akshare_source.py` 添加重试和更真实的请求头：

```python
import requests
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 创建带重试的session
def create_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': 'https://quote.eastmoney.com/',
    })
    return session
```

### 方案B: 使用已有数据复制

如果只需要今天的数据，可以从已有的 `data_gpsj_day_20260421` 复制结构，然后：

1. 从 `monitor_gp_sssj_20260423` 获取实时数据
2. 转换为 `data_gpsj_day` 格式

```python
def create_from_monitor(date: str):
    """从monitor表创建data_gpsj_day数据"""
    monitor_table = f"monitor_gp_sssj_{date}"
    target_table = f"data_gpsj_day_{date}"
    
    sql = f"""
    INSERT INTO {target_table} 
    SELECT 
        NULL as `index`,
        stock_code,
        CONCAT('{date[:4]}-{date[4:6]}-{date[6:]}', ' 00:00:00') as trade_time,
        CONCAT('{date[:4]}-{date[4:6]}-{date[6:]}') as trade_date,
        open,
        close,
        high,
        low,
        volume,
        amount,
        change_pct,
        change,
        turnover_ratio,
        pre_close
    FROM {monitor_table}
    """
```

### 方案C: 延迟执行

如果网络问题是临时的，可以：

1. 记录需要采集的日期
2. 定时重试（如每小时一次）
3. 成功后更新状态

---

## 建议

由于网络问题复杂，建议采用 **方案B**（从monitor表复制）作为临时方案，确保今天数据可用。同时尝试 **方案A** 修复AKShare作为长期方案。

---

**状态**: 需要进一步决策
