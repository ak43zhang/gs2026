# pytdx/mootdx 通达信数据源接入方案

## 一、方案概述

### 1.1 目标
用 pytdx 替代当前 adata/akshare 网页接口，作为 `monitor_bond.py` 的可转债实时数据源。

### 1.2 核心优势
| 对比项 | adata/akshare（当前） | pytdx（目标） |
|--------|---------------------|---------------|
| 数据来源 | 网页爬虫 | TDX HQ服务器直连 |
| 限流风险 | 有（IP封禁、频率限制） | 无（TCP私有协议） |
| 延迟 | 2-5秒 | <1秒 |
| 全市场耗时 | 3-10秒 | <0.5秒 |
| 稳定性 | 依赖网站可用性 | 仅TDX大版本升级影响 |
| 盘口数据 | 不完整 | 五档完整 |
| 与交易同源 | 否 | 是（华泰通达信同服务器） |

### 1.3 技术路线选择

| 方式 | 说明 | 推荐 |
|------|------|------|
| **pytdx.hq（HQ服务器直连）** | 通过TCP连接通达信行情服务器，获取实时Quotes和分钟K线 | ✅ 首选 |
| pytdx.reader（本地文件读取） | 读取TDX软件写入的.lc1/.day二进制文件 | 备选（盘中实时性差） |
| mootdx | pytdx的高层封装，API更简洁 | 可选（底层同pytdx） |

**推荐方案**：使用 `pytdx.hq.TdxHq_API` 直连HQ服务器。原因：
- 实时性最好（不依赖TDX软件写文件的延迟）
- 不需要TDX软件运行也能获取数据
- 同样无限流、无封禁
- 华泰通达信用的是同一批HQ服务器

---

## 二、架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                     TDX HQ 行情服务器                            │
│  (119.147.212.81:7709 / 华泰专用服务器 等)                       │
└──────────────────────────────┬──────────────────────────────────┘
                               │ TCP (pytdx私有协议)
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│              tdx_data_source.py（新模块）                         │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ TdxBondDataSource                                        │   │
│  │                                                          │   │
│  │  1. connect() - 连接HQ服务器（自动选最快的）              │   │
│  │  2. get_all_bonds() - 获取全市场可转债列表                │   │
│  │  3. get_realtime_quotes() - 实时行情（分批，80只/请求）   │   │
│  │  4. get_minute_bars() - 1分钟K线（计算min1指标）          │   │
│  │  5. build_df_now() - 组装成 monitor_bond 需要的 DataFrame │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────┘
                               │ DataFrame (同构)
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│              monitor_bond.py（现有逻辑不变）                      │
│                                                                  │
│  df_now = tdx_source.build_df_now()   ← 替换原 adata 调用       │
│  run_quant_screen_on_tick(df_now, ...)                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、数据字段映射

### 3.1 monitor_bond.py 需要的 df_now 列

| 列名 | 含义 | 数据来源 |
|------|------|----------|
| `bond_code` | 转债代码（6位） | 转债列表 |
| `bond_name` | 转债名称 | 转债列表 |
| `price` | 当前价/最新价 | `get_security_quotes()` → price |
| `open` | 今开 | quotes → open |
| `high` | 最高 | quotes → high |
| `low` | 最低 | quotes → low |
| `pre_close` | 昨收 | quotes → last_close |
| `volume` | 成交量（手） | quotes → vol |
| `amount` | 成交额（元） | quotes → amount |
| `change_pct` | 当日涨跌幅(%) | 计算: (price - pre_close) / pre_close * 100 |
| `min1_amount` | 最近1分钟成交额 | `get_security_bars(1min)` 最新bar的amount |
| `min1_change_pct` | 最近1分钟涨幅(%) | 计算: (bar[-1].close - bar[-2].close) / bar[-2].close * 100 |
| `is_body_up` | 1分钟K线是否阳线 | 1 if bar[-1].close > bar[-1].open else 0 |
| `amount_rank` | 成交额排名 | 计算: df['amount'].rank(ascending=False) |
| `bid1`~`bid5` | 买一~买五价 | quotes → bid prices |
| `ask1`~`ask5` | 卖一~卖五价 | quotes → ask prices |

### 3.2 pytdx API 返回字段

**get_security_quotes() 返回：**
```python
{
    'code': '123257',
    'open': 105.0,
    'high': 106.5,
    'low': 104.8,
    'price': 105.5,       # 最新价
    'last_close': 104.2,  # 昨收
    'vol': 15230,         # 成交量（股/张）
    'amount': 16067650.0, # 成交额（元）
    'bid1': 105.45,       # 买一价
    'bid_vol1': 50,       # 买一量
    'ask1': 105.50,       # 卖一价
    'ask_vol1': 30,       # 卖一量
    # ... bid2-5, ask2-5
}
```

**get_security_bars(category=8, count=3) 返回（1分钟K线）：**
```python
[
    {'open': 104.5, 'close': 105.0, 'high': 105.2, 'low': 104.3, 'vol': 1200, 'amount': 1260000},
    {'open': 105.0, 'close': 105.3, 'high': 105.5, 'low': 105.0, 'vol': 800, 'amount': 843000},
    {'open': 105.3, 'close': 105.5, 'high': 105.6, 'low': 105.2, 'vol': 600, 'amount': 633000},
]
```

---

## 四、核心实现逻辑

### 4.1 连接管理
```python
from pytdx.hq import TdxHq_API

class TdxBondDataSource:
    # 通达信HQ服务器列表（自动选最快的）
    HQ_SERVERS = [
        ('119.147.212.81', 7709),
        ('114.80.63.12', 7709),
        ('218.75.126.9', 7709),
        ('124.160.88.183', 7709),
        # 华泰专用服务器（需确认）
    ]
    
    def connect(self):
        """连接最快的HQ服务器"""
        self.api = TdxHq_API()
        # 自动测速选服务器，或直接连指定服务器
        self.api.connect(host, port)
```

### 4.2 获取全市场可转债代码
```python
def get_bond_list(self):
    """获取沪深全部可转债代码列表"""
    # 方式1：从本地维护的转债列表读取
    # 方式2：通过pytdx获取板块成分股
    # 方式3：从MySQL已有的转债表读取
    # 推荐方式3：复用现有的转债代码表
```

### 4.3 批量获取实时行情
```python
def get_realtime_quotes(self, codes: list) -> pd.DataFrame:
    """批量获取实时行情（每次最多80只）"""
    all_quotes = []
    for batch in chunked(codes, 80):
        # market: 0=深圳, 1=上海
        quotes = self.api.get_security_quotes(
            [(market, code) for market, code in batch]
        )
        all_quotes.extend(quotes)
    return pd.DataFrame(all_quotes)
```

### 4.4 获取1分钟K线（计算min1指标）
```python
def get_min1_data(self, codes: list) -> dict:
    """获取最近2根1分钟K线（用于计算min1_change_pct和min1_amount）"""
    result = {}
    for market, code in codes:
        # category=8 表示1分钟K线, count=2 取最近2根
        bars = self.api.get_security_bars(8, market, code, 0, 2)
        if bars and len(bars) >= 2:
            result[code] = bars
    return result
```

### 4.5 1分钟指标计算（固定分钟边界）

```python
class Min1BarBuilder:
    """
    固定分钟边界的1分钟K线构建器
    
    原理：
    - 每3秒收到一次tick快照（price, total_amount）
    - 按分钟整点切割bar（09:31, 09:32, ...）
    - 指标基于【上一根已完成的bar】计算，不用当前未完成bar
    
    数据结构：
    - current_bar: 当前正在构建的bar (open, high, low, close, amount_start, amount_end)
    - prev_bar: 上一根已完成的bar
    - prev_prev_bar: 再前一根已完成的bar
    """
    
    def __init__(self):
        self._bars = {}  # {bond_code: {current_minute, current_bar, prev_bar, prev_prev_bar}}
    
    def update(self, code, price, total_amount, timestamp):
        """每tick调用，更新bar构建"""
        minute_key = timestamp.strftime('%H:%M')  # 固定分钟边界
        
        state = self._bars.setdefault(code, {
            'current_minute': minute_key,
            'current_bar': {'open': price, 'high': price, 'low': price, 'close': price,
                           'amount_start': total_amount, 'amount_end': total_amount},
            'prev_bar': None,
            'prev_prev_bar': None,
        })
        
        if minute_key != state['current_minute']:
            # 分钟切换：当前bar完成，轮转
            state['prev_prev_bar'] = state['prev_bar']
            state['prev_bar'] = state['current_bar']
            state['current_bar'] = {
                'open': price, 'high': price, 'low': price, 'close': price,
                'amount_start': total_amount, 'amount_end': total_amount,
            }
            state['current_minute'] = minute_key
        else:
            # 同一分钟内：更新OHLC
            bar = state['current_bar']
            bar['high'] = max(bar['high'], price)
            bar['low'] = min(bar['low'], price)
            bar['close'] = price
            bar['amount_end'] = total_amount
    
    def get_min1_metrics(self, code) -> dict:
        """获取基于上一根完整bar的1分钟指标"""
        state = self._bars.get(code)
        if not state or not state['prev_bar']:
            return {'min1_change_pct': 0, 'min1_amount': 0, 'is_body_up': 0}
        
        prev = state['prev_bar']
        prev_prev = state['prev_prev_bar']
        
        # min1_amount = 上一根bar内的成交额
        min1_amount = prev['amount_end'] - prev['amount_start']
        
        # min1_change_pct = 上一根bar的close相对再前一根bar的close的变化
        if prev_prev and prev_prev['close'] > 0:
            min1_change_pct = (prev['close'] - prev_prev['close']) / prev_prev['close'] * 100
        else:
            min1_change_pct = 0
        
        # is_body_up = 上一根bar的阳线判断
        is_body_up = 1 if prev['close'] > prev['open'] else 0
        
        return {
            'min1_change_pct': round(min1_change_pct, 4),
            'min1_amount': round(min1_amount, 2),
            'is_body_up': is_body_up,
        }
```

**性能**：纯内存计算，480只债的bar更新 + 指标计算 < 10ms。

---

## 五、文件规划

```
src/gs2026/monitor/
├── tdx_data_source.py     ← 新增：pytdx数据源模块
├── monitor_bond.py        ← 修改：数据源切换（可配置）
└── ...

scripts/huatai_trader/
├── test_tdx_source.py     ← 新增：测试脚本（明天用）
└── ...

configs/huatai_trader/
└── config.yaml            ← 新增 data_source 配置段
```

### config.yaml 新增段
```yaml
# ==================== Data Source - 数据源 ====================
data_source:
  # Provider: "tdx" | "adata" (fallback)
  provider: "tdx"
  
  # TDX HQ servers (auto-select fastest)
  tdx_servers:
    - { host: "119.147.212.81", port: 7709 }
    - { host: "114.80.63.12", port: 7709 }
    - { host: "218.75.126.9", port: 7709 }
  
  # Connection timeout (seconds)
  connect_timeout: 5
  
  # Reconnect on failure
  auto_reconnect: true
  
  # Fallback to adata if TDX fails
  fallback_enabled: true
```

---

## 六、测试脚本设计（明天验证用）

`scripts/huatai_trader/test_tdx_source.py`

```python
"""
测试内容：
1. 连接TDX HQ服务器（测速选最快）
2. 获取全市场可转债实时行情
3. 获取1分钟K线数据
4. 计算衍生字段（min1_change_pct等）
5. 输出DataFrame样本，验证数据完整性
6. 连续运行60秒，验证稳定性和耗时
"""
```

### 测试输出示例
```
[1] 服务器连接: 119.147.212.81:7709 延迟 45ms ✓
[2] 转债列表: 483只
[3] 实时行情: 483只 耗时 320ms ✓
    - 123257 美诺转债 105.50 涨1.25% 成交额1607万
    - 127060 天赐转债 112.30 涨0.85% 成交额923万
    ...
[4] 1分钟数据: 计算完成 耗时 180ms ✓
    - min1_change_pct 范围: -2.1% ~ +3.4%
    - min1_amount 范围: 0 ~ 5200万
[5] 同构DataFrame: 483行 x 15列 ✓
    columns: [bond_code, bond_name, price, open, high, low, pre_close, 
              volume, amount, change_pct, min1_amount, min1_change_pct, 
              is_body_up, amount_rank, ...]
[6] 稳定性测试: 20轮/60秒 平均耗时 450ms 最大 620ms ✓
```

---

## 七、实施步骤

| 步骤 | 内容 | 时间 |
|------|------|------|
| 1 | 安装 pytdx (`pip install pytdx`) | 今天 |
| 2 | 编写测试脚本 `test_tdx_source.py` | 今天 |
| 3 | 明天开盘验证数据 | 明天 09:30 |
| 4 | 确认数据稳定后，编写 `tdx_data_source.py` | 明天 |
| 5 | 修改 monitor_bond.py 接入新数据源 | 明天 |
| 6 | 并行运行新旧数据源对比验证 | 明天 |

---

## 八、风险与注意事项

| 风险 | 应对 |
|------|------|
| TDX服务器偶尔断连 | 自动重连 + 多服务器轮换 |
| 非交易时段无实时数据 | 正常，只在交易时段运行 |
| TDX大版本升级协议变更 | 半年~一年一次，关注pytdx更新 |
| 1分钟K线逐只获取太慢 | 用本地缓存增量计算（方案A） |
| 转债列表变动（新上市/退市） | 每日盘前从MySQL刷新列表 |

---

**文档版本**: v1.0  
**最后更新**: 2026-07-14
