# Baostock 数据采集并发优化设计文档

**文档版本**: v1.0  
**创建日期**: 2026-04-17  
**作者**: AI Assistant  
**目标文件**: `baostock_collection_v2.py`

---

## 一、现状分析

### 1.1 当前实现问题

| 问题 | 描述 | 影响 |
|------|------|------|
| **串行获取** | 使用 `for` 循环逐个获取股票数据 | 速度极慢，N只股票 = N次网络请求 |
| **单线程** | 无并发机制，CPU/网络利用率低 | 资源浪费 |
| **重复登录** | 每次 `stock_update` 都登录/登出 | 额外开销 |
| **数据库连接** | 每个股票单独写入 | 事务开销大 |

### 1.2 性能估算

假设：
- 股票数量: 5000只
- 单只股票请求时间: 0.5秒 (含网络延迟)
- 单只股票数据处理+写入: 0.1秒

**当前串行模式**:
```
总时间 = 5000 × (0.5 + 0.1) = 3000秒 = 50分钟
```

**目标并发模式** (10线程):
```
总时间 ≈ 5000 × 0.5 / 10 + 5000 × 0.1 = 250 + 500 = 750秒 = 12.5分钟
```

**预期提升**: **4倍加速**

---

## 二、设计方案

### 2.1 核心思路

```
┌─────────────────────────────────────────────────────────────┐
│                    并发采集架构                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  股票代码队列  │───▶│  工作线程池   │───▶│  结果收集队列 │  │
│  │  (Queue)     │    │  (ThreadPool)│    │  (Queue)     │  │
│  └──────────────┘    └──────┬───────┘    └──────┬───────┘  │
│                             │                    │          │
│                             ▼                    ▼          │
│                      ┌──────────────┐    ┌──────────────┐  │
│                      │  Baostock API │    │  批量写入DB  │  │
│                      │  (query_history)│   │  (to_sql)   │  │
│                      └──────────────┘    └──────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 关键技术选型

| 技术 | 选择 | 原因 |
|------|------|------|
| **并发模型** | `concurrent.futures.ThreadPoolExecutor` | 简单易用，自动管理线程池 |
| **线程数** | 10 (可配置) | 平衡速度与API限制 |
| **异常处理** | `try-except` + 失败重试队列 | 确保数据完整性 |
| **批量写入** | 每N条批量写入 | 减少数据库事务开销 |
| **进度监控** | `tqdm` 进度条 | 实时显示采集进度 |

### 2.3 函数设计

#### 2.3.1 核心函数重构

```python
# 原函数 (串行)
def get_multiple_stocks(stock_code: str, ...) -> Optional[pd.DataFrame]

# 新函数 (并发)
def fetch_single_stock(stock_code: str, start_date: str, end_date: str, 
                       max_retries: int = 3) -> Optional[pd.DataFrame]
    """获取单只股票数据（带重试机制）"""
    
def fetch_stocks_concurrent(stock_codes: List[str], start_date: str, end_date: str,
                            max_workers: int = 10) -> List[pd.DataFrame]
    """并发获取多只股票数据"""
```

#### 2.3.2 批量写入优化

```python
def batch_insert_to_db(dfs: List[pd.DataFrame], table_name: str, 
                       batch_size: int = 100) -> None:
    """批量写入数据库，减少事务开销"""
```

### 2.4 错误处理策略

```python
class FetchResult:
    """采集结果封装"""
    stock_code: str
    success: bool
    data: Optional[pd.DataFrame]
    error: Optional[str]
    retry_count: int
```

**失败处理**:
1. 单只股票失败 → 重试3次
2. 连续失败 → 记录到失败列表
3. 全部完成后 → 输出失败统计

### 2.5 配置参数

```python
@dataclass
class BaostockConfig:
    max_workers: int = 10          # 并发线程数
    batch_size: int = 100          # 批量写入大小
    max_retries: int = 3           # 单只股票最大重试
    retry_delay: float = 1.0       # 重试间隔(秒)
    enable_progress: bool = True   # 是否显示进度条
```

---

## 三、API 限制与注意事项

### 3.1 Baostock API 限制

- **登录限制**: 一个账号同时只能有一个登录会话
- **频率限制**: 官方未明确，建议控制并发数 ≤ 10
- **超时处理**: 网络请求设置合理超时

### 3.2 数据库优化

- **连接池**: 使用 `create_engine` 的 `pool_size` 参数
- **批量写入**: 避免单条 `INSERT`，使用 `to_sql` 批量模式
- **索引优化**: 确保 `data_gpsj_day_*` 表有合适索引

---

## 四、实现步骤

### Step 1: 创建 v2 版本文件
- 复制 `baostock_collection.py` → `baostock_collection_v2.py`

### Step 2: 添加并发基础设施
- 导入 `concurrent.futures`
- 添加 `FetchResult` 数据类
- 添加 `BaostockConfig` 配置类

### Step 3: 重构核心函数
- 重写 `get_multiple_stocks` → `fetch_single_stock`
- 新增 `fetch_stocks_concurrent` 并发函数
- 新增 `batch_insert_to_db` 批量写入

### Step 4: 重写主流程
- 修改 `stock_update_v2` 使用并发模式
- 添加进度条显示
- 添加失败重试和统计

### Step 5: 测试验证
- 对比 v1 和 v2 的执行时间
- 验证数据完整性
- 测试异常处理

---

## 五、预期效果

| 指标 | 当前(v1) | 目标(v2) | 提升 |
|------|---------|---------|------|
| 5000只股票采集 | ~50分钟 | ~12分钟 | **4x** |
| CPU利用率 | ~10% | ~60% | 6x |
| 网络利用率 | 低 | 高 | - |
| 失败重试 | 无 | 自动3次重试 | - |
| 进度可见性 | 无 | 实时进度条 | - |

---

## 六、回滚方案

如果 v2 出现问题，立即回滚到 v1:

```bash
# 恢复原始文件
git checkout HEAD -- baostock_collection.py

# 删除 v2 文件
rm baostock_collection_v2.py
```

---

## 七、后续优化方向

1. **异步IO**: 使用 `asyncio` + `aiohttp` 进一步提升性能
2. **分布式采集**: 多机器分片采集
3. **增量更新**: 只采集新增/变化的数据
4. **缓存机制**: Redis缓存热点数据

---

*文档创建时间: 2026-04-17 09:30*
