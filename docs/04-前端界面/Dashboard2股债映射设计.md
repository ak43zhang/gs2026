# Dashboard2 股票-债券-行业映射集成设计方案

**文档版本**: v1.0  
**创建日期**: 2026-03-30  
**状态**: 已确定，待实施  

---

## 1. 项目概述

### 1.1 目标
为 Dashboard2 数据监控中的「股票上攻排行」功能增加债券和行业信息展示，通过 Redis 缓存股票-债券-行业映射关系，提升查询性能。

### 1.2 设计原则
- **非侵入式**: 在原有数据结构基础上扩展，不破坏现有接口
- **高性能**: 使用 Redis 缓存，避免频繁查询数据库
- **可维护**: 定时更新机制，自动化运维

---

## 2. Redis 缓存设计

### 2.1 数据结构设计

#### 2.1.1 主映射表 (Hash)
```
Key: stock_bond_mapping:{date}
Type: Hash
TTL: 7天（自动过期）

Field: {stock_code}
Value: JSON String
```

**示例:**
```
Key: stock_bond_mapping:2026-03-30

Field: "002049"
Value: {
    "stock_code": "002049",
    "stock_name": "紫光国微",
    "bond_code": "127038",
    "bond_name": "国微转债",
    "industry_name": "半导体"
}

Field: "688372"
Value: {
    "stock_code": "688372",
    "stock_name": "伟测科技",
    "bond_code": "118055",
    "bond_name": "伟测转债",
    "industry_name": "半导体"
}
```

#### 2.1.2 最新日期标记 (String)
```
Key: stock_bond_mapping:latest_date
Type: String
Value: "2026-03-30"
```

#### 2.1.3 映射元数据 (String)
```
Key: stock_bond_mapping:meta
Type: String
Value: JSON
```

**示例:**
```json
{
    "created_at": "2026-03-30 03:16:11",
    "total_count": 295,
    "price_range": [120.0, 250.0],
    "bond_daily_date": "2026-03-26",
    "version": "1.0"
}
```

### 2.2 数据更新机制

#### 2.2.1 更新触发条件
- **定时更新**: 每天 09:00（开盘前）自动执行
- **手动更新**: 提供管理接口，支持手动触发
- **首次访问**: 缓存不存在时自动创建

#### 2.2.2 更新流程
```
1. 调用 get_stock_bond_industry_mapping() 生成映射
2. 生成日期键: stock_bond_mapping:{today}
3. 使用 Redis Pipeline 批量写入 Hash
4. 更新 latest_date 标记
5. 更新 meta 元数据
6. 设置 7 天 TTL
```

#### 2.2.3 数据一致性保障
- 更新时创建新日期的 Key，不覆盖旧数据
- 旧数据通过 TTL 自动过期
- latest_date 标记指向最新数据

---

## 3. 后端 API 设计

### 3.1 缓存工具类

**文件路径**: `F:\pyworkspace2026\gs2026\src\gs2026\utils\stock_bond_mapping_cache.py`

```python
"""
股票-债券-行业映射 Redis 缓存工具
"""

import json
from typing import Optional, Dict, List
from datetime import datetime
import pandas as pd

from gs2026.utils import redis_util, log_util
from gs2026.monitor.stock_bond_industry_mapping import get_stock_bond_industry_mapping

logger = log_util.get_logger(__name__)

# Redis Key 常量
REDIS_KEY_PREFIX = "stock_bond_mapping"
REDIS_KEY_LATEST_DATE = f"{REDIS_KEY_PREFIX}:latest_date"
REDIS_KEY_META = f"{REDIS_KEY_PREFIX}:meta"


class StockBondMappingCache:
    """股票-债券-行业映射缓存管理器"""
    
    def __init__(self, redis_client=None):
        self.redis = redis_client or redis_util.get_redis()
    
    def _get_mapping_key(self, date: str) -> str:
        """获取指定日期的映射 Key"""
        return f"{REDIS_KEY_PREFIX}:{date}"
    
    def update_mapping(
        self,
        min_bond_price: float = 120.0,
        max_bond_price: float = 250.0,
        redemption_days_threshold: int = 30,
        force: bool = False
    ) -> Dict:
        """
        更新映射缓存
        
        Args:
            min_bond_price: 最小债券价格
            max_bond_price: 最大债券价格
            redemption_days_threshold: 赎回日期阈值
            force: 是否强制更新（即使已存在）
        
        Returns:
            更新结果信息
        """
        today = datetime.now().strftime('%Y-%m-%d')
        mapping_key = self._get_mapping_key(today)
        
        # 检查是否已存在
        if not force and self.redis.exists(mapping_key):
            logger.info(f"映射缓存已存在: {mapping_key}")
            return {
                "success": True,
                "message": "缓存已存在，跳过更新",
                "date": today,
                "exists": True
            }
        
        try:
            # 生成映射数据
            logger.info("开始生成股票-债券-行业映射...")
            mapping_df = get_stock_bond_industry_mapping(
                min_bond_price=min_bond_price,
                max_bond_price=max_bond_price,
                redemption_days_threshold=redemption_days_threshold
            )
            
            total_count = len(mapping_df)
            logger.info(f"生成映射记录: {total_count} 条")
            
            # 使用 Pipeline 批量写入
            pipe = self.redis.pipeline()
            
            for _, row in mapping_df.iterrows():
                stock_code = str(row['stock_code'])
                data = {
                    "stock_code": stock_code,
                    "stock_name": str(row['short_name']) if pd.notna(row['short_name']) else "",
                    "bond_code": str(row['bond_code']) if pd.notna(row['bond_code']) else "",
                    "bond_name": str(row['bond_name']) if pd.notna(row['bond_name']) else "",
                    "industry_name": str(row['industry_name']) if pd.notna(row['industry_name']) else ""
                }
                pipe.hset(mapping_key, stock_code, json.dumps(data))
            
            # 设置 7 天过期
            pipe.expire(mapping_key, 7 * 24 * 3600)
            
            # 更新最新日期标记
            pipe.set(REDIS_KEY_LATEST_DATE, today)
            
            # 更新元数据
            meta = {
                "created_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "total_count": total_count,
                "price_range": [min_bond_price, max_bond_price],
                "bond_daily_date": self._get_bond_daily_date(),
                "version": "1.0"
            }
            pipe.set(REDIS_KEY_META, json.dumps(meta))
            
            # 执行 Pipeline
            pipe.execute()
            
            logger.info(f"映射缓存更新成功: {mapping_key}, 共 {total_count} 条")
            
            return {
                "success": True,
                "message": "缓存更新成功",
                "date": today,
                "total_count": total_count,
                "exists": False
            }
            
        except Exception as e:
            logger.error(f"更新映射缓存失败: {e}")
            return {
                "success": False,
                "message": f"更新失败: {str(e)}",
                "date": today,
                "exists": False
            }
    
    def get_mapping(self, stock_code: str, date: str = None) -> Optional[Dict]:
        """
        获取单只股票映射
        
        Args:
            stock_code: 股票代码
            date: 指定日期，默认使用最新日期
        
        Returns:
            映射数据字典，不存在返回 None
        """
        if date is None:
            date = self.get_latest_date()
        
        if date is None:
            return None
        
        mapping_key = self._get_mapping_key(date)
        data = self.redis.hget(mapping_key, str(stock_code))
        
        if data:
            return json.loads(data)
        return None
    
    def get_all_mapping(self, date: str = None) -> Dict[str, Dict]:
        """
        获取全部映射
        
        Args:
            date: 指定日期，默认使用最新日期
        
        Returns:
            {stock_code: mapping_data} 字典
        """
        if date is None:
            date = self.get_latest_date()
        
        if date is None:
            return {}
        
        mapping_key = self._get_mapping_key(date)
        all_data = self.redis.hgetall(mapping_key)
        
        return {
            k: json.loads(v) for k, v in all_data.items()
        }
    
    def get_latest_date(self) -> Optional[str]:
        """获取最新映射日期"""
        date = self.redis.get(REDIS_KEY_LATEST_DATE)
        return date.decode('utf-8') if date else None
    
    def get_meta(self) -> Optional[Dict]:
        """获取映射元数据"""
        meta = self.redis.get(REDIS_KEY_META)
        if meta:
            return json.loads(meta)
        return None
    
    def is_cache_valid(self) -> bool:
        """
        检查缓存是否有效（是否为今天）
        
        Returns:
            True: 缓存有效
            False: 缓存不存在或过期
        """
        latest_date = self.get_latest_date()
        if latest_date is None:
            return False
        
        today = datetime.now().strftime('%Y-%m-%d')
        return latest_date == today
    
    def ensure_cache(self, **kwargs) -> bool:
        """
        确保缓存存在（不存在则自动创建）
        
        Returns:
            True: 缓存可用
            False: 创建失败
        """
        if self.is_cache_valid():
            return True
        
        result = self.update_mapping(**kwargs)
        return result["success"]
    
    def _get_bond_daily_date(self) -> str:
        """获取债券日行情最新日期（从数据库）"""
        try:
            from sqlalchemy import create_engine, text
            from gs2026.utils import config_util
            
            url = config_util.get_config("common.url")
            engine = create_engine(url, pool_recycle=3600)
            
            with engine.connect() as conn:
                result = conn.execute(text("SELECT MAX(date) FROM data_bond_daily"))
                date = result.fetchone()[0]
                return str(date) if date else ""
        except Exception as e:
            logger.warning(f"获取债券日行情日期失败: {e}")
            return ""


# 全局缓存实例
cache = None

def get_cache() -> StockBondMappingCache:
    """获取全局缓存实例（单例模式）"""
    global cache
    if cache is None:
        cache = StockBondMappingCache()
    return cache
```

### 3.2 定时任务配置

**文件路径**: `F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\cron\stock_bond_mapping_cron.py`

```python
"""
股票-债券-行业映射定时更新任务
"""

from gs2026.utils.stock_bond_mapping_cache import get_cache
from gs2026.utils import log_util

logger = log_util.get_logger(__name__)


def daily_update():
    """每日更新映射缓存"""
    logger.info("执行每日映射缓存更新...")
    
    cache = get_cache()
    result = cache.update_mapping(force=True)
    
    if result["success"]:
        logger.info(f"映射缓存更新成功: {result.get('total_count', 0)} 条")
    else:
        logger.error(f"映射缓存更新失败: {result.get('message', '未知错误')}")
    
    return result


# 供 APScheduler 使用的配置
SCHEDULE_CONFIG = {
    "id": "stock_bond_mapping_daily_update",
    "func": daily_update,
    "trigger": "cron",
    "hour": 9,
    "minute": 0,
    "description": "每日09:00更新股票-债券-行业映射缓存"
}
```

### 3.3 API 接口扩展

**文件路径**: `F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\stock_bond_mapping.py`

```python
"""
股票-债券-行业映射 API
"""

from flask import Blueprint, jsonify
from gs2026.utils.stock_bond_mapping_cache import get_cache

bp = Blueprint('stock_bond_mapping', __name__, url_prefix='/api/stock-bond-mapping')


@bp.route('/status', methods=['GET'])
def get_status():
    """获取缓存状态"""
    cache = get_cache()
    
    return jsonify({
        "success": True,
        "latest_date": cache.get_latest_date(),
        "is_valid": cache.is_cache_valid(),
        "meta": cache.get_meta()
    })


@bp.route('/update', methods=['POST'])
def force_update():
    """手动触发更新"""
    cache = get_cache()
    result = cache.update_mapping(force=True)
    return jsonify(result)


@bp.route('/<stock_code>', methods=['GET'])
def get_mapping(stock_code):
    """获取单只股票映射"""
    cache = get_cache()
    
    # 确保缓存存在
    if not cache.ensure_cache():
        return jsonify({
            "success": False,
            "message": "缓存创建失败"
        }), 500
    
    mapping = cache.get_mapping(stock_code)
    
    return jsonify({
        "success": True,
        "exists": mapping is not None,
        "data": mapping
    })
```

---

## 4. 前端显示设计

### 4.1 数据接口扩展

**原有股票上攻排行接口**: `GET /api/monitor/stock-rising`

**返回数据结构扩展**:

```json
{
  "success": true,
  "data": [
    {
      "rank": 1,
      "code": "002049",
      "name": "紫光国微",
      "price": 45.20,
      "change": 5.8,
      "change_pct": 5.8,
      "speed": 2.1,
      "volume": 123456,
      "amount": 5678901,
      "bond_code": "127038",
      "bond_name": "国微转债",
      "industry": "半导体"
    },
    {
      "rank": 2,
      "code": "688372",
      "name": "伟测科技",
      "price": 78.50,
      "change": 4.5,
      "change_pct": 4.5,
      "speed": 1.8,
      "volume": 98765,
      "amount": 4321098,
      "bond_code": "118055",
      "bond_name": "伟测转债",
      "industry": "半导体"
    },
    {
      "rank": 3,
      "code": "000001",
      "name": "平安银行",
      "price": 12.30,
      "change": 2.1,
      "change_pct": 2.1,
      "speed": 0.8,
      "volume": 567890,
      "amount": 6987654,
      "bond_code": "-",
      "bond_name": "-",
      "industry": "-"
    }
  ],
  "total": 50,
  "timestamp": "2026-03-30T09:30:00+08:00"
}
```

**后端实现**:

```python
def get_stock_rising_data():
    """获取股票上攻排行数据（含债券信息）"""
    from gs2026.utils.stock_bond_mapping_cache import get_cache
    
    # 1. 查询股票数据（现有逻辑）
    stocks = query_stock_rising_from_mysql()
    
    # 2. 获取映射缓存
    cache = get_cache()
    cache.ensure_cache()  # 确保缓存存在
    
    # 3. 补充债券和行业信息
    for stock in stocks:
        mapping = cache.get_mapping(stock['code'])
        if mapping:
            stock['bond_code'] = mapping['bond_code']
            stock['bond_name'] = mapping['bond_name']
            stock['industry'] = mapping['industry_name']
        else:
            stock['bond_code'] = '-'
            stock['bond_name'] = '-'
            stock['industry'] = '-'
    
    return stocks
```

### 4.2 前端表格设计

**文件路径**: `F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor_stock_rising.html`

**表格列配置**:

| 列名 | 字段 | 宽度 | 对齐 | 说明 |
|------|------|------|------|------|
| 排名 | rank | 60px | 居中 | 原字段 |
| 股票代码 | code | 80px | 居中 | 原字段 |
| 股票名称 | name | 100px | 左对齐 | 原字段 |
| 所属行业 | industry | 100px | 左对齐 | **新增** |
| 最新价 | price | 80px | 右对齐 | 原字段 |
| 涨幅% | change_pct | 80px | 右对齐 | 原字段 |
| 涨速 | speed | 80px | 右对齐 | 原字段 |
| 债券代码 | bond_code | 80px | 居中 | **新增** |
| 债券名称 | bond_name | 120px | 左对齐 | **新增** |

**HTML 结构**:

```html
<table id="stock-rising-table" class="data-table">
  <thead>
    <tr>
      <th class="col-rank">排名</th>
      <th class="col-code">股票代码</th>
      <th class="col-name">股票名称</th>
      <th class="col-industry">所属行业</th>
      <th class="col-price">最新价</th>
      <th class="col-change">涨幅%</th>
      <th class="col-speed">涨速</th>
      <th class="col-bond-code">债券代码</th>
      <th class="col-bond-name">债券名称</th>
    </tr>
  </thead>
  <tbody>
    <!-- 动态生成 -->
  </tbody>
</table>
```

**JavaScript 渲染**:

```javascript
// 渲染表格行
function renderStockRow(stock) {
    const hasBond = stock.bond_code && stock.bond_code !== '-';
    
    return `
        <tr data-code="${stock.code}">
            <td class="col-rank">${stock.rank}</td>
            <td class="col-code">${stock.code}</td>
            <td class="col-name">${stock.name}</td>
            <td class="col-industry">${stock.industry || '-'}</td>
            <td class="col-price">${stock.price.toFixed(2)}</td>
            <td class="col-change ${stock.change_pct >= 0 ? 'up' : 'down'}">
                ${stock.change_pct >= 0 ? '+' : ''}${stock.change_pct.toFixed(2)}%
            </td>
            <td class="col-speed">${stock.speed.toFixed(2)}</td>
            <td class="col-bond-code">${hasBond ? stock.bond_code : '-'}</td>
            <td class="col-bond-name">${hasBond ? stock.bond_name : '-'}</td>
        </tr>
    `;
}
```

### 4.3 样式设计

**CSS**:

```css
/* 表格样式 */
#stock-rising-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}

#stock-rising-table th {
    background: #f5f5f5;
    padding: 10px 8px;
    font-weight: 600;
    border-bottom: 2px solid #ddd;
    white-space: nowrap;
}

#stock-rising-table td {
    padding: 8px;
    border-bottom: 1px solid #eee;
}

/* 列宽 */
.col-rank { width: 60px; text-align: center; }
.col-code { width: 80px; text-align: center; }
.col-name { width: 100px; text-align: left; }
.col-industry { width: 100px; text-align: left; color: #666; }
.col-price { width: 80px; text-align: right; }
.col-change { width: 80px; text-align: right; font-weight: 600; }
.col-speed { width: 80px; text-align: right; }
.col-bond-code { width: 80px; text-align: center; color: #1890ff; }
.col-bond-name { width: 120px; text-align: left; color: #1890ff; }

/* 涨跌幅颜色 */
.col-change.up { color: #f5222d; }
.col-change.down { color: #52c41a; }

/* 无债券时的样式 */
.col-bond-code:contains('-'),
.col-bond-name:contains('-'),
.col-industry:contains('-') {
    color: #999;
}

/* 行悬停效果 */
#stock-rising-table tbody tr:hover {
    background: #f0f5ff;
}
```

---

## 5. 实施计划

### 5.1 文件清单

| 序号 | 文件路径 | 操作 | 说明 |
|------|----------|------|------|
| 1 | `src/gs2026/utils/stock_bond_mapping_cache.py` | 创建 | Redis 缓存工具类 |
| 2 | `src/gs2026/dashboard2/cron/stock_bond_mapping_cron.py` | 创建 | 定时更新任务 |
| 3 | `src/gs2026/dashboard2/routes/stock_bond_mapping.py` | 创建 | 管理 API 接口 |
| 4 | `src/gs2026/dashboard2/routes/monitor.py` | 修改 | 集成缓存查询 |
| 5 | `templates/monitor_stock_rising.html` | 修改 | 增加债券/行业列 |
| 6 | `static/css/monitor.css` | 修改 | 新增样式 |
| 7 | `static/js/pages/monitor-stock-rising.js` | 修改 | 渲染逻辑 |
| 8 | `app.py` | 修改 | 注册 Blueprint 和定时任务 |

### 5.2 实施步骤

```
阶段1: 后端缓存 (2小时)
  ├── 创建 stock_bond_mapping_cache.py
  ├── 创建 stock_bond_mapping_cron.py
  ├── 创建 stock_bond_mapping.py API
  └── 测试缓存功能

阶段2: 数据接口集成 (1小时)
  ├── 修改 monitor.py 股票上攻排行接口
  ├── 集成缓存查询逻辑
  └── 测试数据返回

阶段3: 前端开发 (2小时)
  ├── 修改 monitor_stock_rising.html
  ├── 修改 monitor-stock-rising.js
  ├── 添加 CSS 样式
  └── 测试显示效果

阶段4: 联调测试 (1小时)
  ├── 端到端测试
  ├── 性能测试
  └── 异常场景测试

总计: 6小时
```

### 5.3 测试用例

| 场景 | 预期结果 |
|------|----------|
| 缓存不存在时访问 | 自动创建缓存，返回正确数据 |
| 有债券映射的股票 | 显示债券代码、名称、行业 |
| 无债券映射的股票 | 显示 "-" |
| 定时任务执行 | 每天09:00自动更新 |
| 手动触发更新 | 立即更新缓存 |
| Redis 故障 | 降级到实时查询数据库 |

---

## 6. 附录

### 6.1 相关文件引用

- 映射生成模块: `src/gs2026/monitor/stock_bond_industry_mapping.py`
- Redis 工具: `src/gs2026/utils/redis_util.py`
- 日志工具: `src/gs2026/utils/log_util.py`

### 6.2 配置参数

```python
# 默认参数
DEFAULT_MIN_BOND_PRICE = 120.0
DEFAULT_MAX_BOND_PRICE = 250.0
DEFAULT_REDEMPTION_DAYS_THRESHOLD = 30

# Redis 配置
REDIS_KEY_PREFIX = "stock_bond_mapping"
REDIS_TTL_DAYS = 7

# 定时任务
CRON_HOUR = 9
CRON_MINUTE = 0
```

### 6.3 版本历史

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-03-30 | 初始设计方案 |

---

**文档结束**
