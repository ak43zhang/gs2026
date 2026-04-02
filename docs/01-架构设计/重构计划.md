# GS2026 Dashboard 模块化重构计划

## 1. 重构目标

### 1.1 核心目标
- 将单体 HTML/JS 拆分为独立模块
- 模块间松耦合，高内聚
- 错误隔离，不影响全局
- 便于测试和维护

### 1.2 重构原则
1. **渐进式重构** - 逐步替换，保持功能
2. **向后兼容** - 不影响现有功能
3. **测试驱动** - 每个模块有单元测试
4. **文档同步** - 重构同时更新文档

---

## 2. 当前架构问题

### 2.1 问题分析
| 问题 | 影响 | 示例 |
|------|------|------|
| 全局变量污染 | 命名冲突 | `addLog` vs `addAnalysisLog` |
| DOM 依赖硬编码 | 元素不存在时报错 | `getElementById('log-container')` |
| 代码重复 | 维护困难 | 多个 Tab 切换逻辑 |
| 错误无隔离 | 一处错误影响全局 | HTML 结构错误导致 JS 失效 |
| 无单元测试 | 难以验证 | 每次修改需手动测试 |

### 2.2 技术债务
- 800+ 行 JavaScript 混合在 HTML 中
- 15+ 个全局函数
- 多处重复的 DOM 操作
- 无错误边界处理

---

## 3. 目标架构

### 3.1 模块划分
```
src/gs2026/dashboard/
├── static/
│   ├── js/
│   │   ├── core/           # 核心框架
│   │   │   ├── app.js      # 应用入口
│   │   │   ├── event-bus.js # 事件总线
│   │   │   ├── logger.js   # 日志管理
│   │   │   └── utils.js    # 工具函数
│   │   ├── modules/        # 业务模块
│   │   │   ├── tab.js      # Tab 切换
│   │   │   ├── service.js  # 服务管理
│   │   │   ├── analysis.js # 分析服务
│   │   │   ├── process.js  # 进程监控
│   │   │   └── log.js      # 日志显示
│   │   └── main.js         # 主入口
│   └── css/
│       ├── base.css        # 基础样式
│       ├── components.css  # 组件样式
│       └── modules.css     # 模块样式
└── templates/
    ├── base.html           # 基础模板
    ├── components/         # 可复用组件
    └── pages/              # 页面模板
```

### 3.2 模块依赖关系
```
                    ┌─────────────┐
                    │   main.js   │
                    └──────┬──────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │  core/app   │ │  core/bus   │ │ core/logger │
    └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
           │               │               │
           └───────────────┼───────────────┘
                           ▼
              ┌─────────────────────────┐
              │      业务模块层          │
              │  ┌─────┐ ┌─────┐ ┌────┐ │
              │  │ tab │ │svc  │ │proc│ │
              │  └─────┘ └─────┘ └────┘ │
              └─────────────────────────┘
```

---

## 4. 重构阶段

### 阶段 1: 基础设施 (Week 1)

#### 4.1.1 创建核心框架
- [ ] 创建 `static/js/core/app.js`
  - 模块注册/获取
  - 生命周期管理
  - 配置管理
- [ ] 创建 `static/js/core/event-bus.js`
  - 发布订阅模式
  - 事件命名空间
- [ ] 创建 `static/js/core/logger.js`
  - 统一日志接口
  - 级别控制
  - 多输出目标
- [ ] 创建 `static/js/core/utils.js`
  - DOM 安全操作
  - 网络请求封装
  - 数据验证

#### 4.1.2 基础样式分离
- [ ] 创建 `static/css/base.css`
  - 重置样式
  - 变量定义
  - 工具类
- [ ] 创建 `static/css/components.css`
  - 按钮
  - 卡片
  - 表单

#### 4.1.3 测试框架
- [ ] 配置 Jest 测试环境
- [ ] 创建测试工具
- [ ] 编写核心模块测试

**交付物:**
- 核心框架代码
- 基础样式文件
- 单元测试覆盖 80%+

---

### 阶段 2: 模块提取 (Week 2-3)

#### 4.2.1 Tab 模块
- [ ] 创建 `modules/tab.js`
  - Tab 状态管理
  - 切换动画
  - 懒加载
- [ ] 创建 `templates/components/tab.html`
- [ ] 编写单元测试

#### 4.2.2 服务管理模块
- [ ] 创建 `modules/service.js`
  - 服务配置管理
  - 启动/停止控制
  - 状态轮询
- [ ] 创建 `templates/components/service-card.html`
- [ ] 编写单元测试

#### 4.2.3 分析服务模块
- [ ] 创建 `modules/analysis.js`
  - 分析服务配置
  - 参数管理
  - 日志显示
- [ ] 创建 `templates/components/analysis-card.html`
- [ ] 编写单元测试

#### 4.2.4 进程监控模块
- [ ] 创建 `modules/process.js`
  - 进程列表
  - 状态显示
  - 停止控制
- [ ] 创建 `templates/components/process-list.html`
- [ ] 编写单元测试

**交付物:**
- 4 个独立模块
- 对应模板文件
- 单元测试

---

### 阶段 3: 页面重构 (Week 4)

#### 4.3.1 基础模板
- [ ] 创建 `templates/base.html`
  - HTML 骨架
  - CSS/JS 引用
  - 全局布局

#### 4.3.2 数据采集页面
- [ ] 创建 `templates/pages/data-collection.html`
  - 使用新模块
  - 保持原有功能

#### 4.3.3 数据分析页面
- [ ] 创建 `templates/pages/data-analysis.html`
  - 使用新模块
  - 保持原有功能

#### 4.3.4 监控页面
- [ ] 创建 `templates/pages/monitor.html`
  - 使用新模块
  - 保持原有功能

**交付物:**
- 3 个重构后的页面
- 功能对比测试报告

---

### 阶段 4: 集成测试 (Week 5)

#### 4.4.1 集成测试
- [ ] 端到端测试
- [ ] 性能测试
- [ ] 兼容性测试

#### 4.4.2 文档更新
- [ ] 更新 API 文档
- [ ] 更新开发文档
- [ ] 编写迁移指南

#### 4.4.3 代码审查
- [ ] 团队审查
- [ ] 安全审查
- [ ] 性能审查

**交付物:**
- 测试报告
- 更新后的文档
- 审查报告

---

### 阶段 5: 上线切换 (Week 6)

#### 4.5.1 灰度发布
- [ ] 并行运行新旧版本
- [ ] 监控错误率
- [ ] 收集反馈

#### 4.5.2 全面切换
- [ ] 切换到新版本
- [ ] 监控 24 小时
- [ ] 回滚预案

#### 4.5.3 旧代码清理
- [ ] 删除旧模板
- [ ] 清理无用代码
- [ ] 归档文档

**交付物:**
- 上线报告
- 监控数据
- 清理后的代码库

---

## 5. 风险控制

### 5.1 风险识别
| 风险 | 概率 | 影响 | 应对策略 |
|------|------|------|---------|
| 功能回归 | 中 | 高 | 完整测试覆盖 |
| 性能下降 | 低 | 中 | 性能基准测试 |
| 浏览器兼容 | 中 | 中 | 多浏览器测试 |
| 开发延期 | 中 | 中 | 分阶段交付 |

### 5.2 回滚策略
1. 保留旧代码分支
2. 配置开关切换
3. 监控关键指标
4. 5 分钟内可回滚

---

## 6. 成功标准

### 6.1 技术指标
- [ ] 代码覆盖率 > 80%
- [ ] 模块间耦合度 < 0.3
- [ ] 页面加载时间 < 2s
- [ ] 错误率 < 0.1%

### 6.2 业务指标
- [ ] 功能完整保留
- [ ] 用户无感知切换
- [ ] 开发效率提升 30%

---

## 7. 时间线

```
Week 1: 基础设施
Week 2: 模块提取 - Tab + 服务
Week 3: 模块提取 - 分析 + 进程
Week 4: 页面重构
Week 5: 集成测试
Week 6: 上线切换
```

---

## 8. 相关文档

- [DESIGN_CONTROL_PAGE.md](./DESIGN_CONTROL_PAGE.md) - 页面设计
- [DESIGN_PROCESS_MONITOR.md](./DESIGN_PROCESS_MONITOR.md) - 进程监控设计
- [DESIGN_WEBSOCKET_NOTIFICATION.md](./DESIGN_WEBSOCKET_NOTIFICATION.md) - WebSocket设计

---

## 9. 附录

### 9.1 命名规范
- 模块: `kebab-case.js`
- 类: `PascalCase`
- 函数: `camelCase`
- 常量: `UPPER_SNAKE_CASE`

### 9.2 文件模板
```javascript
// module-name.js
GS2026.register('module-name', {
    config: {},
    
    init() {
        // 初始化
    },
    
    destroy() {
        // 清理
    }
});
```

### 9.3 测试模板
```javascript
// module-name.test.js
describe('ModuleName', () => {
    beforeEach(() => {
        // 准备
    });
    
    test('should do something', () => {
        // 测试
    });
});
```
