# 数据监控页面懒加载设计方案

## 当前问题

### 现状
- 页面加载后立即启动定时刷新 (`startAutoRefresh()`)
- 每3秒刷新一次，无论页面是否可见
- 只有部分API调用有 `document.hidden` 检查

### 影响
- 不必要的网络请求
- 后台运行时浪费资源
- 增加服务器负载

---

## 懒加载方案

### 方案A：Page Visibility API（推荐）

使用 `document.visibilityState` 检测页面可见性，只在可见时刷新数据。

#### 实现代码

```javascript
// ===== 懒加载控制 =====
let _autoRefreshTimer = null;
let _isPageVisible = true;

// 监听页面可见性变化
document.addEventListener('visibilitychange', () => {
    _isPageVisible = document.visibilityState === 'visible';
    
    if (_isPageVisible) {
        // 页面可见：立即刷新并启动定时器
        console.log('[LazyLoad] Page visible, resuming refresh');
        loadAllData();
        startAutoRefresh();
    } else {
        // 页面不可见：停止定时器
        console.log('[LazyLoad] Page hidden, pausing refresh');
        stopAutoRefresh();
    }
});

function startAutoRefresh() {
    stopAutoRefresh();
    
    // 页面不可见时不启动
    if (!_isPageVisible) {
        console.log('[LazyLoad] Page not visible, skip startAutoRefresh');
        return;
    }
    
    _autoRefreshTimer = setInterval(() => {
        // 双重检查：定时器触发时再次确认页面可见
        if (_isLive && document.visibilityState === 'visible') {
            loadTimestamps();
            loadAllData();
        }
    }, REFRESH_INTERVAL);
}

function stopAutoRefresh() {
    if (_autoRefreshTimer) {
        clearInterval(_autoRefreshTimer);
        _autoRefreshTimer = null;
    }
}

// 初始化时检查页面可见性
if (document.visibilityState === 'visible') {
    loadTimestamps();
    loadAllData();
    startAutoRefresh();
} else {
    console.log('[LazyLoad] Page initially hidden, deferring load');
}
```

#### 优点
- 简单可靠
- 浏览器原生支持
- 即时响应（切换标签页时立即暂停/恢复）

#### 缺点
- 需要浏览器支持（现代浏览器都支持）

---

### 方案B：Intersection Observer（备选）

当监控组件进入视口时才加载数据。

#### 适用场景
- 页面有多个监控区域
- 只想加载可见区域的数据

#### 实现代码

```javascript
// 使用 IntersectionObserver 监听元素可见性
const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            // 元素进入视口，加载数据
            loadAllData();
            startAutoRefresh();
        } else {
            // 元素离开视口，停止刷新
            stopAutoRefresh();
        }
    });
});

// 观察主容器
observer.observe(document.querySelector('.container'));
```

#### 优点
- 更精细的控制（可以按组件懒加载）

#### 缺点
- 复杂度较高
- 滚动时可能频繁触发

---

## 推荐方案：方案A（Page Visibility API）

### 理由
1. 数据监控页面需要整体刷新，不需要按组件控制
2. 实现简单，改动小
3. 浏览器兼容性良好

### 修改范围

| 文件 | 修改内容 |
|------|---------|
| `monitor.html` | 添加 visibilitychange 事件监听，修改初始化和刷新逻辑 |

### 代码变更

```javascript
// 1. 添加状态变量
let _isPageVisible = true;

// 2. 添加事件监听
document.addEventListener('visibilitychange', handleVisibilityChange);

// 3. 实现处理函数
function handleVisibilityChange() {
    _isPageVisible = !document.hidden;
    if (_isPageVisible) {
        loadAllData();
        startAutoRefresh();
    } else {
        stopAutoRefresh();
    }
}

// 4. 修改初始化
if (!document.hidden) {
    loadTimestamps();
    loadAllData();
    startAutoRefresh();
}

// 5. 修改 startAutoRefresh
function startAutoRefresh() {
    stopAutoRefresh();
    if (document.hidden) return; // 页面不可见不启动
    
    _autoRefreshTimer = setInterval(() => {
        if (_isLive && !document.hidden) {
            loadTimestamps();
            loadAllData();
        }
    }, REFRESH_INTERVAL);
}
```

---

## 预期效果

### 场景1：用户切换到其他标签页
- **当前**：继续每3秒刷新
- **优化**：立即停止刷新

### 场景2：用户最小化浏览器
- **当前**：继续每3秒刷新
- **优化**：立即停止刷新

### 场景3：用户切换回页面
- **当前**：可能已经错过数据更新
- **优化**：立即刷新一次，恢复定时刷新

---

## 兼容性

| 浏览器 | 支持版本 |
|--------|---------|
| Chrome | 33+ |
| Firefox | 18+ |
| Safari | 7+ |
| Edge | 12+ |

所有现代浏览器都支持。

---

## 实施建议

1. **测试场景**
   - 切换标签页时观察控制台日志
   - 最小化浏览器后观察网络请求
   - 返回页面时确认立即刷新

2. **回滚方案**
   - 保留原有代码注释
   - 使用 feature flag 控制

---

*设计日期: 2026-04-01*
*状态: 待确认*
