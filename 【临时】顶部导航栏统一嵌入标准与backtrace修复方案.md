# 顶部导航栏统一嵌入标准（含股债交集回溯修复）

**分析日期**: 2026-08-04  
**状态**: 待审核  
**目标**: 确立全站统一的导航栏嵌入规范，修复 backtrace 页面，并作为**以后所有新页面的标准**

---

## 一、全站导航机制普查（代码实测）

扫描 `templates/*.html` 全部页面，导航机制分布：

| 机制 | 页面 | 占比 |
|------|------|------|
| **`nav-placeholder` + `initNav()`（JS动态）** | dashboard、index、monitor、review（分析中心/复盘）、market_review、range_analysis（区间测算）、stock_picker（交叉行概选股）等 | **绝大多数（主流标准）** |
| `{% include 'nav.html' %}`（服务端include） | **仅 backtrace.html（异类）** | 1个 |

**结论**：全站统一标准 = **`nav-placeholder` + `nav.js` 的 `initNav()`**。backtrace 是唯一不合规页面。

---

## 二、统一标准（黄金模板）

以"分析中心/复盘"(review.html)、"区间测算"(range_analysis.html)为黄金模板，标准三要素：

### 要素1：head 引入 nav.js 依赖的 CSS
```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/base.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/components.css') }}">
<!-- 页面自己的CSS -->
```

### 要素2：body 第一个元素放导航占位符
```html
<body>
    <div id="nav-placeholder"></div>
    <!-- 页面主体 -->
    ...
```

### 要素3：body 末尾引入 nav.js 并初始化
```html
    <script src="{{ url_for('static', filename='js/nav.js') }}"></script>
    <script>initNav('<activeKey>');</script>
</body>
```

### activeKey 取值规范（实测 nav.js 定义）

| activeKey | 对应主菜单 | 适用页面 |
|-----------|-----------|---------|
| `'dashboard'` | 首页/仪表盘 | dashboard |
| `'monitor'` | 实时监控 | monitor |
| `'picker'` | 智能选股 | stock_picker、range_analysis、**backtrace** |
| `'review'` | 分析中心/复盘 | review、market_review |
| ...（以 nav.js 中 NAV 定义为准） | | |

> **股债交集回溯属于"智能选股"大类** → 用 `initNav('picker')`，与区间测算完全一致。

---

## 三、backtrace.html 具体修改

### 3.1 顶部（删除服务端include，改占位符）

**删除**:
```html
{% set page_title = '智能选股' %}
{% set active_page = 'picker' %}
{% include 'nav.html' %}
```

**替换为**:
```html
<div id="nav-placeholder"></div>
```

### 3.2 底部（`</body>` 前新增）

```html
<script src="{{ url_for('static', filename='js/nav.js') }}"></script>
<script>initNav('picker');</script>
```

> 注意：backtrace.html 底部已有 `<script src=".../backtrace.js">`，nav.js 应在 backtrace.js **之前或之后均可**（无依赖），建议放 backtrace.js 之前，先渲染导航。

### 3.3 CSS 核对
backtrace.html 当前已引入 base.css、components.css、backtrace.css。需核对是否与 range_analysis 一致（nav.js 生成的导航若依赖额外CSS，一并补齐）。实施时以 range_analysis 的 head 为准逐条对齐。

### 3.4 子导航（页面内二级tab）保留
backtrace 页面内的子导航（🎯交叉行概选股/📈涨停/📊区间测算/🔍股债交集回溯）是**页面级二级tab**，与顶部主导航无关，**保留不动**。

---

## 四、以后新增页面的统一规范（沉淀为团队标准）

> **任何新页面接入导航栏，必须遵循以下3步，禁止使用 `{% include 'nav.html' %}`**

1. **head**：引入 `base.css` + `components.css`（+ 页面自身CSS）
2. **body 首行**：`<div id="nav-placeholder"></div>`
3. **body 末尾**：引入 `nav.js` + 调用 `initNav('<activeKey>')`
4. 若新页面属于某个已有大类（如智能选股），复用对应 activeKey；若是全新大类，需先在 `nav.js` 的菜单定义中新增菜单项，再使用新 activeKey

建议把此规范写入项目开发文档（如 `docs/` 或 README），供后续开发遵循。

---

## 五、验证清单

- [ ] backtrace 顶部导航栏与"区间测算/交叉行概选股"**视觉完全一致**（logo、菜单项、样式、响应式）
- [ ] 顶部"智能选股"菜单高亮
- [ ] 页面内子导航正常，"股债交集回溯"tab高亮
- [ ] 无控制台报错（nav.js 正常初始化）
- [ ] CSS 无缺失（导航样式完整）

---

## 六、风险评估

| 风险 | 说明 | 对策 |
|------|------|------|
| CSS 缺失 | nav.js 生成HTML依赖特定CSS类 | 对齐 range_analysis 的 head |
| nav.html 是否还被其他页面用 | 若仅 backtrace 用，改后 nav.html 可保留不删 | 不删除 nav.html，仅改 backtrace 引用方式 |
| 脚本顺序 | nav.js 与 backtrace.js 顺序 | 二者无依赖，nav.js 先加载渲染导航 |

改动极小（顶部3行→1行 + 底部加2行 + CSS核对），风险低。

---

## 七、需你确认

1. 确立统一标准 = **`nav-placeholder` + `nav.js` `initNav()`**（禁用 include nav.html），并作为以后新页面规范？
2. backtrace 用 `initNav('picker')`（归入智能选股大类）？
3. 是否要把"统一导航规范"写入项目开发文档（docs/），供后续遵循？

---

**等待审核**
