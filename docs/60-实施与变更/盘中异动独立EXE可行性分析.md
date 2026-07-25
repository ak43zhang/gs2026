# 盘中异动 独立EXE - 纯展示端方案（待审核）

**文档版本**: v2.0（纯展示端）
**生成时间**: 2026-07-25 09:54
**状态**: 🟡 待审核
**前置**: 盘中异动独立EXE可行性分析.md v1.0

---

## 一、你的思路完全正确 —— 而且比想象更简单

**前提**：MySQL + Redis 已部署上线，数据由服务器端的采集/AI进程持续写入。
**exe职责**：只连数据库**读数据 + 展示效果**，不碰采集、不碰AI分析。

这样一来，exe从"启动一条流水线"退化成"一个只读Web展示端"，**复杂度下降一个数量级**。

### 对比：复杂度骤降

| 维度 | 原方案(全流水线) | 纯展示端方案 |
|------|------------------|--------------|
| 需启动进程数 | 5个(monitor+3AI+web) | **1个(仅web展示)** |
| AI引擎依赖 | 必须(volcengine/deepseek) | **完全不需要** ✅ |
| 浏览器自动化 | deepseek要Chrome | **不需要** ✅ |
| 数据源依赖 | 要实时行情源 | **不需要** ✅ |
| 打包体积 | 150-300MB | **~30-40MB** |
| 打包难度 | 🔴高 | 🟢低 |
| 稳定性 | 中 | **高** |

---

## 二、验证结论：展示层本就以"读"为主

我扫了 `anomaly.py` 的全部10个路由，绝大多数是纯读：

| 路由 | 类型 | 纯展示端 |
|------|------|----------|
| `/anomaly` (页面) | 读 | ✅ 保留 |
| `/api/anomaly/list` (异动列表) | 读 | ✅ 保留 |
| `/api/anomaly/stats` (统计) | 读 | ✅ 保留 |
| `/api/anomaly/mainlines` (主线) | 读 | ✅ 保留 |
| `/api/anomaly/potential/latest` (最新潜在) | 读 | ✅ 保留 |
| `/api/anomaly/potential/history` (历史) | 读 | ✅ 保留 |
| `/api/anomaly/potential/replay-times` (回放) | 读 | ✅ 保留 |
| `/api/anomaly/latest-trading-date` | 读 | ✅ 保留 |
| `/api/anomaly/potential` (POST主动挖掘) | **写+AI** | ⛔ 禁用 |
| `/api/anomaly/list` 内的重置逻辑 | **写** | ⛔ 跳过 |

**只有2处非纯读**（主动挖掘触发AI、卡死记录重置），展示端**直接禁用**即可——这些是服务器端进程的活儿，展示端不该做。

### 前端刷新机制（利好）
`anomaly.html` 用 `setInterval(loadData, 30000)` **每30秒轮询HTTP** —— 纯REST，**无WebSocket依赖**，完美适配独立展示端。

---

## 三、纯展示端 exe 架构

```
┌─────────────────────────────────────────┐
│         盘中异动展示.exe                   │
│  ┌───────────────────────────────────┐  │
│  │ 内嵌轻量 Flask (仅异动展示相关路由) │  │
│  │  - /anomaly 页面                   │  │
│  │  - /api/anomaly/* 只读接口         │  │
│  └───────────────┬───────────────────┘  │
│                  │ 只读SQL                │
└──────────────────┼───────────────────────┘
                   ▼
        ┌──────────────────────┐
        │  MySQL(已上线)        │ ← 服务器端进程持续写入
        │  Redis(已上线)        │
        └──────────────────────┘
                   ▲
        双击exe → 浏览器自动打开 http://localhost:PORT/anomaly
```

**exe内只保留**：
- Flask + 异动展示Blueprint（只读版）
- `anomaly.html` 模板 + 静态资源
- MySQL/Redis 只读连接
- 配置读取（config_util）

**exe内剔除**：
- ❌ monitor_stock（数据生产）
- ❌ anomaly_analyzer/correlator/potential（AI分析）
- ❌ volcengine/deepseek（AI引擎）
- ❌ akshare/tushare/playwright等采集库
- ❌ dashboard2其他所有功能（只留异动）

---

## 四、需要的改造（很小）

### 4.1 抽取只读展示模块
新建 `standalone/anomaly_viewer/`，包含：
- `app.py` — 精简Flask，只注册异动Blueprint
- `anomaly_routes.py` — 从`anomaly.py`复制，**去掉写/AI的2个路由**
- `templates/anomaly.html` — 复制
- `config.yaml` — 外置DB/Redis配置

### 4.2 剥离AI/写依赖
`anomaly.py` 顶部 `from ...anomaly_potential import ...` 这些**延迟import**（在函数内），只要不调用那2个写路由，就不会触发AI库导入 → 打包时可安全排除。

### 4.3 只读数据库账号（企业级建议）
给exe用**只读MySQL账号**，从数据库层面杜绝误写：
```sql
CREATE USER 'gs_viewer'@'%' IDENTIFIED BY 'xxx';
GRANT SELECT ON gs.* TO 'gs_viewer'@'%';
```

---

## 五、打包方案

```bash
pip install pyinstaller
pyinstaller --onefile --name 盘中异动展示 ^
    --add-data "templates;templates" ^
    --add-data "config.yaml;." ^
    --hidden-import pymysql ^
    --exclude-module playwright ^
    --exclude-module akshare ^
    --exclude-module tushare ^
    --exclude-module selenium ^
    app.py
```

用 `--exclude-module` 排除采集/AI/浏览器大库，体积可压到 30-40MB。

---

## 六、双击exe后的体验

```
双击 盘中异动展示.exe
  ├─ 读取同目录 config.yaml (MySQL/Redis地址)
  ├─ 检查数据库连通（连不上→弹窗提示）
  ├─ 启动内嵌Flask (随机端口或固定5001)
  ├─ 自动打开浏览器 → http://localhost:5001/anomaly
  └─ 托盘/控制台显示"运行中"
       页面每30秒自动刷新，展示最新异动+主线+潜在标的
```

---

## 七、待你确认清单

```
□ 确认采用"纯展示端"方案?（我认为这是最优解）
□ 是否需要"潜在标的"POST主动挖掘功能?（涉及AI,建议禁用,只看已生成结果）
□ 数据库是否用只读账号 gs_viewer?（推荐,防误写）
□ 展示端口固定(如5001)还是随机?
□ 是否需要托盘图标/后台运行?还是控制台窗口即可?
□ 除"盘中异动"外,是否还想把"主线""潜在标的"等同页展示?(它们本就在同一页)
```

---

## 八、实施交付物（审核通过后）

| 交付物 | 说明 |
|--------|------|
| `standalone/anomaly_viewer/app.py` | 精简Flask展示端 |
| `standalone/anomaly_viewer/anomaly_routes.py` | 只读路由 |
| `standalone/anomaly_viewer/templates/` | 页面模板 |
| `config.yaml` | 外置配置 |
| `build_exe.bat` | 打包脚本 |
| `盘中异动展示.exe` | 最终产物(~35MB) |
| `使用说明.md` | 操作手册 |

---

## 九、风险（已大幅降低）

| 风险 | 等级 | 应对 |
|------|------|------|
| DB连接配置错误 | 🟡 低 | 启动检查+友好提示 |
| 端口占用 | 🟡 低 | 可配置/自动换端口 |
| 非交易时段无当日数据 | 🟡 低 | 展示历史日期数据 |
| 打包漏依赖 | 🟢 极低 | 只读展示依赖简单 |

**没有🔴/🟠风险了** —— 因为剥离了AI/采集/浏览器这些最麻烦的部分。

---

**结论**: 你的判断非常准。"只读展示端"是最优方案 —— 简单、稳定、体积小、无AI依赖。请确认§七的6项，我即可进入实施。
