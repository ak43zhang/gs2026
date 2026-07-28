# 监控页面时段化API控制方案 v3.0

> **版本**: v3.0  
> **日期**: 2026-07-28  
> **状态**: 待审核  
> **核心目标**: 节省后端查询接口不断刷新的问题 — 前端直接判断时段，非必要时段零API调用

---

## 一、需求确认（已确认）

| 时段 | 行为 | API触发 |
|------|------|---------|
| **00:00-09:25** | 前端判断，**完全不触发任何后端API** | 零调用 |
| **09:25-09:30** | **只大盘概览API**，有数据后展示并停止；其他API**完全不触发** | 仅 `/api/monitor/market-overview` |
| **09:30-15:00** | **实时正常刷新**（所有API） | 全部正常 |
| **15:00后** | **只刷新一次**，展示最后一个tick后停止；**时间轴可点击** | 仅首次调用全部API，之后零调用 |

**关键修复**: 15:00后当前无法点击时间轴 → 修复为可点击

---

## 二、当前实现问题分析

### 当前问题

| 问题 | 当前行为 | 期望行为 |
|------|----------|----------|
| 1 | 00:00-09:25仍触发API（只是后端报错） | **前端零触发** |
| 2 | 09:25-09:30可能触发排行API | **只大盘概览** |
| 3 | 15:00后完全停止（包括时间轴） | **只刷新一次+时间轴可用** |
| 4 | 时段判断分散在多个函数 | **统一前端时段判断** |

### 当前代码结构问题

```javascript
// 当前：时段判断分散，15:00后isNonTradingHours=true导致时间轴也禁用
function isNonTradingHours() {
    return (timeVal < 925) || (timeVal > 1130 && timeVal < 1300) || (timeVal > 1500);
    // 15:00后返回true，导致所有刷新停止，包括时间轴
}
```

---

## 三、修复方案 v3.0

### 核心设计：三层控制架构

```
┌─────────────────────────────────────────┐
│  第一层：时段状态机（统一判断）            │
│  - getTradingPhase() 返回当前时段          │
│  - 'night' | 'auction' | 'trading' | 'closed' │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│  第二层：API触发控制器                   │
│  - shouldCallMarketOverview() 大盘概览?  │
│  - shouldCallRankings() 排行API?         │
│  - shouldEnableTimeline() 时间轴可用?      │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│  第三层：执行层（loadAllData等）          │
│  - 根据控制器决定是否实际调用API         │
│  - 15:00后只执行一次标记                 │
└─────────────────────────────────────────┘
```

### 具体修改点

#### 修改1：新增时段状态机（统一判断）

```javascript
// 新增：统一时段判断（替代分散的 isTradingHours/isAuctionHours/isNonTradingHours）
function getTradingPhase() {
    const timeVal = getCurrentTimeVal();
    
    if (timeVal < 925) {
        return 'night';        // 00:00-09:25：夜间/早盘前
    } else if (timeVal >= 925 && timeVal < 930) {
        return 'auction';      // 09:25-09:30：集合竞价
    } else if (timeVal >= 930 && timeVal <= 1500) {
        return 'trading';      // 09:30-15:00：交易时段
    } else {
        return 'closed';       // 15:00后：收盘
    }
}

// 新增：15:00后是否已刷新过标记
let _closedPhaseDataLoaded = false;
```

#### 修改2：新增API触发控制器

```javascript
// 大盘概览API是否应该调用
function shouldCallMarketOverview() {
    const phase = getTradingPhase();
    
    switch (phase) {
        case 'night':
            return false;  // 夜间不调用
        case 'auction':
            // 集合竞价：只调用一次（成功加载后不再调用）
            return !_auctionDataLoaded;
        case 'trading':
            return true;   // 交易时段正常调用
        case 'closed':
            // 15:00后：只调用一次
            return !_closedPhaseDataLoaded;
    }
}

// 排行API（stock/bond/industry）是否应该调用
function shouldCallRankings() {
    const phase = getTradingPhase();
    
    switch (phase) {
        case 'night':
        case 'auction':
            return false;  // 夜间和集合竞价不调用排行
        case 'trading':
            return true;   // 交易时段正常调用
        case 'closed':
            // 15:00后：只调用一次
            return !_closedPhaseDataLoaded;
    }
}

// 时间轴是否应该可用（核心修复：15:00后时间轴可用）
function shouldEnableTimeline() {
    const phase = getTradingPhase();
    
    // 关键修复：所有时段时间轴都可用（包括15:00后）
    // 只有"完全无数据"时才禁用
    if (_timestamps.length === 0 && phase === 'night') {
        return false;  // 夜间且无历史数据
    }
    return true;  // 其他时段（包括15:00后）都可用
}

// 自动刷新是否应该启动
function shouldStartAutoRefresh() {
    const phase = getTradingPhase();
    return phase === 'trading';  // 只有交易时段才自动刷新
}
```

#### 修改3：修改 loadAllData（核心执行层）

```javascript
async function loadAllData(timeStr) {
    // 历史日期回放模式：不受时段限制，直接加载
    if (timeStr || getSelectedDate()) {
        console.log('[loadAllData] 历史回放模式，加载全部数据');
        await loadMarketStats(timeStr);
        await loadStockRanking(timeStr);
        await loadBondRanking(timeStr);
        await loadIndustryRanking(timeStr);
        await loadCombineSignal(timeStr);
        return;
    }
    
    // 实时模式：根据时段控制API调用
    const phase = getTradingPhase();
    console.log('[loadAllData] 实时模式，当前时段:', phase);
    
    switch (phase) {
        case 'night':
            // 00:00-09:25：零API调用
            console.log('[loadAllData] 夜间时段，不触发任何API');
            updateTradingStatusHint();
            return;
            
        case 'auction':
            // 09:25-09:30：只大盘概览
            if (shouldCallMarketOverview()) {
                console.log('[loadAllData] 集合竞价，只加载大盘概览');
                await loadAuctionMarketOverview();  // 成功后内部标记_auctionDataLoaded
            } else {
                console.log('[loadAllData] 集合竞价，大盘概览已加载');
            }
            updateTradingStatusHint();
            return;
            
        case 'trading':
            // 09:30-15:00：正常加载全部
            console.log('[loadAllData] 交易时段，正常加载全部');
            await loadMarketStats();
            await loadStockRanking();
            await loadBondRanking();
            await loadIndustryRanking();
            await loadCombineSignal();
            _closedPhaseDataLoaded = false;  // 重置15:00后标记
            return;
            
        case 'closed':
            // 15:00后：只加载一次
            if (!_closedPhaseDataLoaded) {
                console.log('[loadAllData] 收盘后，加载最后一次数据');
                await loadMarketStats();
                await loadStockRanking();
                await loadBondRanking();
                await loadIndustryRanking();
                await loadCombineSignal();
                _closedPhaseDataLoaded = true;
                console.log('[loadAllData] 收盘数据已加载，停止自动刷新');
            } else {
                console.log('[loadAllData] 收盘数据已加载，跳过');
            }
            return;
    }
}
```

#### 修改4：修改 startAutoRefresh（自动刷新控制）

```javascript
function startAutoRefresh() {
    // 历史日期不启动
    if (getSelectedDate()) {
        console.log('[AutoRefresh] 历史日期，不启动');
        return;
    }
    
    // 【关键】只有交易时段才启动自动刷新
    if (!shouldStartAutoRefresh()) {
        console.log('[AutoRefresh] 非交易时段，不启动自动刷新');
        return;
    }
    
    stopAutoRefresh();
    
    _autoRefreshTimer = setInterval(() => {
        if (_isLive && !document.hidden && shouldStartAutoRefresh()) {
            loadTimestamps();
            loadAllData();
        }
    }, REFRESH_INTERVAL);
    
    console.log('[AutoRefresh] 已启动，间隔:', REFRESH_INTERVAL);
}
```

#### 修改5：修改时间轴相关函数（15:00后可点击）

```javascript
// 修改：更新时间轴可用状态
function updateTimelineAvailability() {
    const timeline = document.getElementById('timeline-container');
    if (!timeline) return;
    
    // 关键修复：根据 shouldEnableTimeline() 而非 isNonTradingHours()
    if (shouldEnableTimeline()) {
        timeline.classList.remove('disabled');
        timeline.style.pointerEvents = 'auto';
        timeline.style.opacity = '1';
    } else {
        timeline.classList.add('disabled');
        timeline.style.pointerEvents = 'none';
        timeline.style.opacity = '0.5';
    }
}

// 修改：时间轴点击处理
function handleTimelineClick(event) {
    // 移除 isNonTradingHours() 检查，改用 shouldEnableTimeline()
    if (!shouldEnableTimeline()) {
        console.log('[Timeline] 当前不可用');
        return;
    }
    
    // ...原有逻辑
}

// 修改：时段检查定时器
function startTradingCheckTimer() {
    if (_tradingCheckTimer) clearInterval(_tradingCheckTimer);
    
    _tradingCheckTimer = setInterval(() => {
        const phase = getTradingPhase();
        
        switch (phase) {
            case 'auction':
                // 集合竞价：重试大盘概览
                if (!_auctionDataLoaded) {
                    loadAuctionMarketOverview();
                }
                break;
                
            case 'trading':
                // 进入交易时段：启动自动刷新
                if (!_autoRefreshTimer && _isLive) {
                    startAutoRefresh();
                }
                if (!_pollingTimer) {
                    adjustPollingInterval(3000);
                }
                break;
                
            case 'closed':
                // 15:00后：停止自动刷新，但时间轴可用
                if (_autoRefreshTimer) {
                    stopAutoRefresh();
                    console.log('[TradingCheck] 15:00后，停止自动刷新');
                }
                // 触发一次数据加载（如果还没加载）
                if (!_closedPhaseDataLoaded) {
                    loadAllData();
                }
                break;
                
            case 'night':
                // 夜间：确保停止
                if (_autoRefreshTimer) stopAutoRefresh();
                if (_pollingTimer) adjustPollingInterval(0);
                break;
        }
        
        // 更新时间轴可用性（关键：15:00后设为可用）
        updateTimelineAvailability();
        updateTradingStatusHint();
        
    }, 30000);  // 30秒检查一次
}
```

#### 修改6：修改提示信息

```javascript
function updateTradingStatusHint() {
    const phase = getTradingPhase();
    const hint = document.getElementById('non-trading-hint');
    if (!hint) return;
    
    switch (phase) {
        case 'night':
            hint.textContent = '⏸️ 非交易时段（00:00-09:25），09:30自动恢复';
            hint.style.display = 'block';
            break;
        case 'auction':
            const status = _auctionDataLoaded ? '✅ 已加载' : '📡 加载中...';
            hint.textContent = `⏸️ 集合竞价（09:25-09:30）${status}，09:30自动恢复`;
            hint.style.display = 'block';
            break;
        case 'trading':
            hint.style.display = 'none';
            break;
        case 'closed':
            hint.textContent = '⏸️ 已收盘（15:00后），点击时间轴查看历史';
            hint.style.display = 'block';
            break;
    }
}
```

---

## 四、删除/废弃的旧代码

```javascript
// 以下函数将被废弃（保留兼容但不再主用）
function isTradingHours() { ... }      // 废弃，用 getTradingPhase()
function isAuctionHours() { ... }      // 废弃，用 getTradingPhase()
function isNonTradingHours() { ... }   // 废弃，用 getTradingPhase()

// 相关调用点替换为新的控制器函数
```

---

## 五、实施检查清单

- [ ] 新增 `getTradingPhase()` 时段状态机
- [ ] 新增 `_closedPhaseDataLoaded` 标记
- [ ] 新增 `shouldCallMarketOverview()` 控制器
- [ ] 新增 `shouldCallRankings()` 控制器
- [ ] 新增 `shouldEnableTimeline()` 控制器（**关键：15:00后可用**）
- [ ] 新增 `shouldStartAutoRefresh()` 控制器
- [ ] 修改 `loadAllData()` 使用新控制器
- [ ] 修改 `startAutoRefresh()` 使用新控制器
- [ ] 修改 `startTradingCheckTimer()` 使用新控制器
- [ ] 修改 `updateTimelineAvailability()` 使用 `shouldEnableTimeline()`
- [ ] 修改 `handleTimelineClick()` 移除 `isNonTradingHours()` 检查
- [ ] 修改 `updateTradingStatusHint()` 使用新时段判断
- [ ] 验证：00:00-09:25 零API调用
- [ ] 验证：09:25-09:30 只大盘概览API
- [ ] 验证：09:30-15:00 正常全部API
- [ ] 验证：15:00后只刷新一次，时间轴可点击

---

## 六、回退方案

```bash
# 备份当前
git tag backup-before-v3-refresh-20260728

# 如需回退
git checkout backup-before-v3-refresh-20260728 -- src/gs2026/dashboard2/templates/monitor.html
```

---

**待审核确认后实施。**
