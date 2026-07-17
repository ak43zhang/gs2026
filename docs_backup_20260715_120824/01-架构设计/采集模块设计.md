# GS2026 数据采集模块设计文档

## 版本记录
| 版本 | 日期 | 修改内容 | 作者 |
|------|------|---------|------|
| v1.0 | 2026-03-26 | 初始设计 | AI Assistant |
| v1.1 | 2026-03-26 | 整合用户反馈，细化基础采集模块 | AI Assistant |
| v1.2 | 2026-03-27 | 调整任务顺序，新增可转债任务，统一风险采集参数 | AI Assistant |

---

## 1. 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    数据采集 Dashboard2                    │
├─────────────────────────────────────────────────────────┤
│  Tab 导航                                                │
│  [开市采集] [基础采集] [消息采集] [风险采集]              │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │              当前运行进程服务                     │   │
│  │  显示所有运行中的采集任务及PID                   │   │
│  └─────────────────────────────────────────────────┘   │
│                                                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │              采集任务卡片网格                     │   │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐  │   │
│  │  │任务1   │ │任务2   │ │任务3   │ │...     │  │   │
│  │  │[启动]  │ │[启动]  │ │[启动]  │ │[启动]  │  │   │
│  │  └────────┘ └────────┘ └────────┘ └────────┘  │   │
│  └─────────────────────────────────────────────────┘   │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## 2. 四大模块详细设计

### 2.1 开市采集模块（Monitor）

**功能定位**：实时市场监控数据采集，持续运行

| 任务ID | 任务名称 | 脚本文件 | 功能描述 | 参数 |
|--------|---------|---------|---------|------|
| stock | 股票监控 | monitor_stock.py | 实时股票数据监控 | 无 |
| bond | 债券监控 | monitor_bond.py | 实时债券数据监控 | 无 |
| industry | 行业监控 | monitor_industry.py | 行业板块数据监控 | 无 |
| dp_signal | 大盘信号 | monitor_dp_signal.py | 大盘指标监控 | 无 |
| gp_zq_signal | 股债联动 | monitor_gp_zq_rising_signal.py | 股债关联监控 | 无 |

**特点**：
- 持续运行，实时监控
- 无日期参数
- 独立进程管理
- 使用 `pythonw.exe` 后台运行

---

### 2.2 基础采集模块（Base）

**功能定位**：基础市场数据批量采集，按日期区间执行

#### 任务列表（按显示顺序）

| 序号 | 任务ID | 任务名称 | 脚本文件 | 函数名 | 参数 |
|------|--------|---------|---------|--------|------|
| 1 | ztb | 涨停板数据 | zt_collection.py | collect_ztb_query | start_date, end_date |
| 2 | zt_zb | 涨停炸板数据 | zt_collection.py | collect_zt_zb_collection | start_date, end_date |
| 3 | zskj | 指数宽基 | base_collection.py | zskj | 无 |
| 4 | today_lhb | 今日龙虎榜 | base_collection.py | today_lhb | start_date, end_date |
| 5 | rzrq | 融资融券 | base_collection.py | rzrq | 无 |
| 6 | gsdt | 公司动态 | base_collection.py | gsdt | start_date, end_date |
| 7 | history_lhb | 历史龙虎榜 | base_collection.py | history_lhb | start_date, end_date |
| 8 | risk_tdx | 通达信风险 | base_collection.py | risk_tdx | start_date, end_date |
| 9 | industry_ths | 同花顺行业 | base_collection.py | industry_ths | 无 |
| 10 | industry_code_component_ths | 同花顺行业成分 | base_collection.py | industry_code_component_ths | 无 |
| 11 | baostock | Baostock数据 | baostock_collection.py | get_baostock_collection | start_date, end_date |
| 12 | wencai_base | 问财基础数据 | wencai_collection.py | collect_base_query | start_date, end_date, headless |
| 13 | wencai_hot | 问财热股数据 | wencai_collection.py | collect_popularity_query | start_date, end_date, headless |
| 14 | bond_base | 可转债base | other/bond_zh_cov.py | get_bond | 无 |
| 15 | bond_daily | 可转债daily | other/bond_zh_cov.py | get_bond_daily | 无 |
| 16 | bk_gn | 板块概念 | bk_gn_collection.py | bk_gn_collect | start_date, end_date |

**参数说明**：
- `start_date`: 开始日期 (YYYY-MM-DD)
- `end_date`: 结束日期 (YYYY-MM-DD)
- `headless`: 是否无头模式 (boolean, 默认True)

**特点**：
- 批量执行，按日期区间采集
- 使用包装脚本调用指定函数
- 显示"执行中"→"已完成"状态

---

### 2.3 消息采集模块（News）

**功能定位**：财经新闻和快讯采集

| 任务ID | 任务名称 | 脚本文件 | 函数名 | 参数 |
|--------|---------|---------|--------|------|
| caijing_zaocan | 财经早餐 | collection_message.py | cjzc_dfcf | date |
| global_news_dc | 全球快讯-东财 | collection_message.py | qqcjkx_dfcf | date |
| global_news_sina | 全球快讯-新浪 | collection_message.py | qqcjkx_xlcj | date |
| news_futu | 快讯-富途 | collection_message.py | kx_ftnn | date |
| live_ths | 财经直播-同花顺 | collection_message.py | qqcjzb_thscj | date |
| cls_history | 财联社历史 | cls_history.py | cjnrjx | date |
| new_stock | 新股申购 | dicj_yckx.py | main | date |
| hot_query | 热门查询 | zqsb_rmcx.py | main | date |
| xinhua | 新华财经 | xhcj.py | main | date |
| hot_api | 热门API | hot_api.py | main | date |

---

### 2.4 风险采集模块（Risk）

**功能定位**：风险预警数据采集

| 任务ID | 任务名称 | 脚本文件 | 函数名 | 参数 |
|--------|---------|---------|--------|------|
| wencai_risk_daily | 问财风险-日 | wencai_risk_history.py | wencai_risk_collect | start_date, end_date |
| wencai_risk_year | 问财风险-年 | wencai_risk_year_history.py | wencai_risk_year_collect | start_date, end_date |
| notice_risk | 公告风险 | notice_risk_history.py | notice_risk_collect | start_date, end_date |
| akshare_risk | Akshare风险 | akshare_risk_history.py | akshare_risk_collect | start_date, end_date |

**参数说明**：
- `start_date`: 开始日期 (YYYY-MM-DD)
- `end_date`: 结束日期 (YYYY-MM-DD)

---

## 3. 配置结构（Python）

```python
COLLECTION_MODULES = {
    'monitor': {
        'name': '开市采集',
        'icon': '📊',
        'type': 'monitor',
        'tasks': { ... }
    },
    'base': {
        'name': '基础采集',
        'icon': '📁',
        'type': 'collection',
        'tasks': { ... }
    },
    'news': {
        'name': '消息采集',
        'icon': '📰',
        'type': 'collection',
        'tasks': { ... }
    },
    'risk': {
        'name': '风险采集',
        'icon': '⚠️',
        'type': 'collection',
        'tasks': { ... }
    }
}
```

---

## 4. 进程管理设计

### 4.1 启动方式

**监控类任务**：
```python
# 直接执行脚本，持续运行
subprocess.Popen(
    [pythonw_exe, script_path],
    creationflags=CREATE_NO_WINDOW,
    startupinfo=STARTUPINFO
)
```

**采集类任务**：
```python
# 生成包装脚本，调用指定函数
wrapper_code = generate_wrapper(service_id, script, function, params)
subprocess.Popen(
    [pythonw_exe, wrapper_path],
    creationflags=CREATE_NO_WINDOW,
    startupinfo=STARTUPINFO
)
```

### 4.2 停止方式

**前缀匹配查找**：
```python
# 提取 service_id 前缀
service_id_prefix = process_id.rsplit('_', 2)[0]

# 在 self.services 中查找
for sid, info in self.services.items():
    if sid.startswith(service_id_prefix):
        # 找到匹配的进程
        
# 在 Redis 中查找
for proc in redis_processes:
    if proc.process_id.startswith(service_id_prefix):
        # 找到匹配的进程
```

### 4.3 状态显示

| 状态 | 颜色 | 说明 |
|------|------|------|
| running | 🟢 绿色 | 监控类任务持续运行 |
| executing | 🟡 黄色 | 采集类任务执行中 |
| completed | 🔵 蓝色 | 采集类任务已完成 |
| stopped | ⚪ 灰色 | 任务已停止 |

---

## 5. API 接口

### 5.1 获取模块列表
```
GET /api/collection/modules
```

### 5.2 获取模块任务
```
GET /api/collection/<module_id>/tasks
```

### 5.3 启动任务
```
POST /api/collection/<module_id>/start/<task_id>
Body: { "start_date": "2026-03-27", "end_date": "2026-03-27" }
```

### 5.4 停止任务
```
POST /api/collection/stop/<process_id>
```

### 5.5 获取状态
```
GET /api/collection/status
```

### 5.6 全部停止
```
POST /api/collection/stopAll
```

---

## 6. 前端交互设计

### 6.1 编辑锁定
```javascript
// 输入框获得焦点时锁定
input.addEventListener('focus', () => {
    this.isEditing = true;
});

// 失去焦点后延迟解锁
input.addEventListener('blur', () => {
    setTimeout(() => { this.isEditing = false; }, 500);
});
```

### 6.2 事件委托
```javascript
// 使用事件委托绑定停止按钮
container.addEventListener('click', (e) => {
    const btn = e.target.closest('.btn-stop-sm');
    if (btn) {
        const processId = btn.dataset.process;
        this.emit('stop', { processId });
    }
});
```

---

## 7. 注意事项

1. **不要修改原有 Dashboard 功能**
2. **所有新方法使用 `pythonw_exe`**
3. **包装脚本使用 `chr(10)` 代替 `\n`**
4. **进程停止使用前缀匹配查找**
5. **编辑时暂停自动刷新**

---

## 8. 更新记录

### v1.2 (2026-03-27)
- 调整基础采集任务顺序（16个任务）
- 新增可转债任务（bond_base、bond_daily）
- 统一风险采集参数为日期区间
- "知识库数据"更名为"指数宽基"
- 添加编辑锁定功能
- 优化进程管理（无弹窗）

### v1.1 (2026-03-26)
- 细化基础采集模块配置
- 添加问财数据采集
- 完善涨停板数据采集

### v1.0 (2026-03-26)
- 初始设计
- 定义四大模块架构

---

## 9. 已知问题与限制

### 9.1 包装脚本问题
- **问题**: 换行符处理在某些情况下可能导致语法错误
- **临时方案**: 使用 `chr(10)` 代替 `\n`
- **长期方案**: 考虑使用模板引擎生成脚本

### 9.2 进程状态同步
- **问题**: 进程停止后，前端状态更新有延迟（最多5秒）
- **原因**: 前端定时刷新机制
- **方案**: 考虑使用 WebSocket 实时推送

### 9.3 Redis 依赖
- **问题**: Redis 连接不稳定时，进程状态可能丢失
- **方案**: 添加本地状态缓存作为备份

### 9.4 参数验证
- **问题**: 前端缺少参数格式验证
- **影响**: 用户可能输入错误格式的参数
- **方案**: 添加参数验证逻辑

### 9.5 并发限制
- **问题**: 快速连续启动多个任务可能出错
- **限制**: 同一任务最多5个实例
- **方案**: 添加队列机制

---

## 10. 待办事项

### 高优先级
- [ ] 解决包装脚本换行符问题
- [ ] 优化进程状态同步机制
- [ ] 添加参数验证

### 中优先级
- [ ] 添加进程日志查看功能
- [ ] 添加任务执行进度显示
- [ ] 优化错误提示

### 低优先级
- [ ] 支持定时任务
- [ ] 支持批量操作
- [ ] 添加任务历史记录

---

## 11. 相关文档

- [TODO.md](./TODO.md) - 完整待办事项清单
- [CHANGELOG.md](./CHANGELOG.md) - 变更日志
- [DASHBOARD2_INTEGRATION.md](./DASHBOARD2_INTEGRATION.md) - Dashboard2 集成指南

