# 量化选债实时命中接入交易助手指南

## 一、接入方式选择

### 方案A：前端JavaScript直接调用（推荐）
在 `monitor.html` 的量化选债模块中，当检测到新的实时命中时，直接调用8081服务。

**优点**：
- 实时性最好，命中立即触发
- 无需修改后端代码
- 弹窗直接显示在操作界面

**缺点**：
- 需要保持页面打开

### 方案B：后端Python调用
在 `quant_screen_core.py` 或 `monitor_bond.py` 中，当检测到命中时调用HTTP接口。

**优点**：
- 不依赖前端页面
- 可以在后台运行

**缺点**：
- 需要额外处理弹窗确认（可能需要改用其他通知方式）

---

## 二、方案A实施：前端JavaScript接入

### 2.1 修改位置
文件：`src/gs2026/dashboard2/templates/monitor.html`

在 `checkNewHits()` 函数中，当检测到新命中时，调用交易助手。

### 2.2 代码实现

在 `monitor.html` 的 `<script>` 部分添加以下代码：

```javascript
// ==================== 交易助手接入 ====================

// 交易助手服务地址
const TRADER_API_URL = 'http://127.0.0.1:8081';

// 已触发交易的债券缓存（防止重复触发）
var _traderTriggeredBonds = {};

// 调用交易助手准备买入
async function callTraderBuy(bondCode, bondName, price, lots) {
    try {
        // 检查是否在交易时段
        var now = new Date();
        var hour = now.getHours();
        var minute = now.getMinutes();
        var time = hour * 100 + minute;
        
        // 交易时段：9:30-11:30, 13:00-15:00
        var isTradingTime = (time >= 930 && time <= 1130) || (time >= 1300 && time <= 1500);
        if (!isTradingTime) {
            console.log('[Trader] 非交易时段，跳过:', bondCode);
            return;
        }
        
        // 检查是否已触发过（同一债券5分钟内不重复触发）
        var cacheKey = bondCode + '_' + now.toDateString();
        if (_traderTriggeredBonds[cacheKey]) {
            var lastTime = _traderTriggeredBonds[cacheKey];
            if (now - lastTime < 5 * 60 * 1000) { // 5分钟
                console.log('[Trader] 5分钟内已触发过，跳过:', bondCode);
                return;
            }
        }
        
        // 调用交易助手HTTP服务
        var response = await fetch(TRADER_API_URL + '/api/prepare_buy', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                code: bondCode,
                name: bondName,
                price: price,
                lots: lots || 1
            })
        });
        
        var result = await response.json();
        if (result.success) {
            // 记录触发时间
            _traderTriggeredBonds[cacheKey] = now;
            console.log('[Trader] 买入准备成功:', result.message);
            // 在页面上显示提示
            showTraderNotification('买入信号', bondCode + ' ' + bondName, 'success');
        } else {
            console.log('[Trader] 买入准备失败:', result.error || result.message);
            if (result.error && result.error.indexOf('用户取消') === -1) {
                showTraderNotification('买入失败', result.error, 'error');
            }
        }
    } catch (e) {
        console.error('[Trader] 调用交易助手失败:', e);
        showTraderNotification('交易助手错误', e.message, 'error');
    }
}

// 显示交易通知
function showTraderNotification(title, message, type) {
    // 创建通知元素
    var div = document.createElement('div');
    div.style.cssText = 'position:fixed;top:60px;right:20px;z-index:9999;padding:12px 16px;border-radius:6px;font-size:13px;max-width:300px;word-break:break-all;transition:all 0.3s;';
    
    if (type === 'success') {
        div.style.background = '#e8f5e9';
        div.style.color = '#2e7d32';
        div.style.border = '1px solid #4caf50';
    } else {
        div.style.background = '#ffebee';
        div.style.color = '#c62828';
        div.style.border = '1px solid #f44336';
    }
    
    div.innerHTML = '<b>' + title + '</b><br>' + message;
    document.body.appendChild(div);
    
    // 3秒后自动消失
    setTimeout(function() {
        div.style.opacity = '0';
        setTimeout(function() {
            if (div.parentNode) div.parentNode.removeChild(div);
        }, 300);
    }, 3000);
}
```

### 2.3 在实时命中处调用

在 `checkNewHits()` 函数中，当检测到新命中时，添加调用代码：

```javascript
// 在 checkNewHits 函数中，处理新数据时添加：

async function checkNewHits() {
    try {
        var r = await fetch('/api/monitor/quant-screen/hits?after_id=' + _lastHitId);
        var res = await r.json();
        if (res.success && res.hits && res.hits.length > 0) {
            // ... 原有代码 ...
            
            // ===== 新增：调用交易助手 =====
            res.hits.forEach(function(hit) {
                // 只处理买入信号（status === 'entry'）
                if (hit.signal_status === 'entry') {
                    callTraderBuy(
                        hit.bond_code,
                        hit.bond_name || '',
                        hit.entry_price,
                        1  // 默认1手
                    );
                }
            });
            // ==============================
        }
    } catch (e) {
        console.error('检查新数据失败:', e);
    }
}
```

---

## 三、方案B实施：后端Python接入

### 3.1 修改位置
文件：`src/gs2026/dashboard2/services/quant_screen_core.py`

### 3.2 代码实现

在检测到实时命中时，调用交易助手：

```python
import requests
import logging

TRADER_API_URL = "http://127.0.0.1:8081"

class QuantScreenCore:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # 已触发缓存
        self._trader_triggered = {}
    
    def _call_trader_buy(self, bond_code: str, bond_name: str, price: float, lots: int = 1):
        """调用交易助手准备买入"""
        try:
            # 检查交易时段
            from datetime import datetime
            now = datetime.now()
            hour, minute = now.hour, now.minute
            time_val = hour * 100 + minute
            
            is_trading = (930 <= time_val <= 1130) or (1300 <= time_val <= 1500)
            if not is_trading:
                self.logger.info(f"[Trader] 非交易时段，跳过: {bond_code}")
                return
            
            # 检查是否已触发过（5分钟内不重复）
            cache_key = f"{bond_code}_{now.date()}"
            if cache_key in self._trader_triggered:
                last_time = self._trader_triggered[cache_key]
                if (now - last_time).seconds < 300:  # 5分钟
                    self.logger.info(f"[Trader] 5分钟内已触发过，跳过: {bond_code}")
                    return
            
            # 调用HTTP接口
            response = requests.post(
                f"{TRADER_API_URL}/api/prepare_buy",
                json={
                    "code": bond_code,
                    "name": bond_name,
                    "price": price,
                    "lots": lots
                },
                timeout=35  # 30秒弹窗超时 + 5秒缓冲
            )
            
            result = response.json()
            if result.get("success"):
                self._trader_triggered[cache_key] = now
                self.logger.info(f"[Trader] 买入准备成功: {result['message']}")
            else:
                self.logger.warning(f"[Trader] 买入准备失败: {result.get('error', '未知错误')}")
                
        except Exception as e:
            self.logger.error(f"[Trader] 调用交易助手失败: {e}")
    
    def on_hit_detected(self, hit: dict):
        """当检测到命中时调用"""
        # ... 原有处理逻辑 ...
        
        # 调用交易助手（只处理买入信号）
        if hit.get('signal_status') == 'entry':
            self._call_trader_buy(
                hit['bond_code'],
                hit.get('bond_name', ''),
                hit['entry_price'],
                1  # 默认1手
            )
```

---

## 四、使用流程

### 4.1 启动服务

1. **启动交易助手服务**（保持运行）：
```bash
cd F:\pyworkspace2026\gs2026
.venv\Scripts\python scripts\huatai_trader\main.py
```

2. **打开数据监控页面**：
   - 访问 `http://localhost:8080/monitor`
   - 确保量化选债模块正常运行

3. **登录华泰证券软件**：
   - 保持华泰软件运行并登录
   - 确保可以正常交易

### 4.2 交易流程

```
1. 量化选债检测到命中信号
   ↓
2. 自动调用交易助手HTTP接口
   ↓
3. 屏幕右下角弹出确认窗口（30秒超时）
   ↓
4. 用户点击"准备委托"
   ↓
5. 系统自动填充华泰软件买入界面
   ↓
6. 用户在华泰软件中确认并点击"买入"
   ↓
7. 交易完成
```

### 4.3 注意事项

- **保持服务运行**：交易助手服务需要一直保持运行
- **保持页面打开**：如使用方案A，需要保持monitor页面打开
- **首次登录**：华泰软件需要首次手动登录，之后保持会话
- **弹窗超时**：30秒内不操作会自动取消
- **重复触发保护**：同一债券5分钟内不会重复触发

---

## 五、测试验证

### 5.1 手动测试API

```bash
# 测试买入准备（会弹出确认窗口）
curl -X POST http://127.0.0.1:8081/api/prepare_buy \
  -H "Content-Type: application/json" \
  -d '{"code":"123257","name":"美诺转债","price":105.20,"lots":1}'

# 测试状态查询
curl http://127.0.0.1:8081/api/status
```

### 5.2 查看日志

```bash
# 实时查看交易助手日志
tail -f scripts/huatai_trader/huatai_trader.log
```

---

## 六、故障排查

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| 弹窗不显示 | 服务未启动 | 检查8081端口是否监听 |
| 华泰窗口未填充 | 软件未运行 | 确保华泰软件已启动并登录 |
| 重复触发 | 缓存失效 | 检查 `_traderTriggeredBonds` 缓存 |
| 非交易时段 | 时间限制 | 只在9:30-11:30, 13:00-15:00工作 |
| HTTP调用失败 | 网络问题 | 检查127.0.0.1:8081是否可访问 |

---

**文档版本**: v1.0  
**最后更新**: 2026-07-14
