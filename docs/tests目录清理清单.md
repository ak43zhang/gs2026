# Tests目录清理清单

## 分析结果

| 统计项 | 数量 |
|--------|------|
| 总文件数 | 32个 |
| Python脚本 | 31个 |
| __init__.py | 1个 |

---

## 一、建议删除的测试脚本

### 1. 临时/诊断脚本（一次性使用）

| 序号 | 文件名 | 说明 | 操作 |
|------|--------|------|------|
| 1 | check_div_balance.py | 检查div平衡 | 删除 |
| 2 | check_env.py | 检查环境 | 删除 |
| 3 | check_html_structure.py | 检查HTML结构 | 删除 |
| 4 | compare_tabs.py | 比较tabs | 删除 |
| 5 | diagnose_news_cls.py | 诊断新闻CLS | 删除 |
| 6 | diagnose_news_cls2.py | 诊断新闻CLS2 | 删除 |
| 7 | final_check.py | 最终检查 | 删除 |
| 8 | find_extra_div.py | 查找额外div | 删除 |
| 9 | list_divs.py | 列出divs | 删除 |

**小计：9个**

### 2. 重复/冗余测试

| 序号 | 文件名 | 说明 | 操作 |
|------|--------|------|------|
| 1 | test_cls_direct.py | 测试CLS直连 | 删除（有test_cls_direct2.py） |
| 2 | test_cls_once.py | 测试CLS一次 | 删除 |
| 3 | test_deepseek_analysis.py | 测试deepseek分析 | 删除（有多个变体） |
| 4 | test_deepseek_combine_collection.py | 测试deepseek合并采集 | 删除 |
| 5 | test_deepseek_combine_ztb_area.py | 测试deepseek涨停板块 | 删除 |
| 6 | test_deepseek_deepseek_analysis_event_driven.py | 测试事件驱动 | 删除 |
| 7 | test_deepseek_deepseek_analysis_news_cls.py | 测试新闻CLS | 删除 |
| 8 | test_deepseek_deepseek_analysis_news_combine.py | 测试新闻合并 | 删除 |
| 9 | test_deepseek_deepseek_analysis_news_ztb.py | 测试新闻涨停 | 删除 |
| 10 | test_deepseek_deepseek_analysis_notice.py | 测试公告分析 | 删除 |

**小计：10个**

### 3. 过时/无用测试

| 序号 | 文件名 | 说明 | 操作 |
|------|--------|------|------|
| 1 | test_control_html.py | 测试控制HTML | 删除 |
| 2 | test_decorators.py | 测试装饰器 | 删除 |
| 3 | test_import_cls.py | 测试导入CLS | 删除 |
| 4 | test_process_monitor.py | 测试进程监控 | 删除 |
| 5 | test_redis_pool.py | 测试Redis池 | 删除 |
| 6 | test_redis_write.py | 测试Redis写入 | 删除 |
| 7 | test_wencai_cookie_v2.py | 测试问财cookie | 删除 |
| 8 | test_wrapper_v2.py | 测试wrapper | 删除 |
| 9 | test_zt_zb.py | 测试涨停炸板 | 删除 |

**小计：9个**

---

## 二、建议保留的测试脚本

| 文件名 | 说明 |
|--------|------|
| run_tests.py | 测试运行器 |
| test_cls_daemon.py | CLS守护进程测试 |
| test_cls_direct2.py | CLS直连测试（较新） |
| __init__.py | Python包标识 |

**小计：4个**

---

## 三、删除清单汇总

| 类别 | 数量 |
|------|------|
| 临时/诊断脚本 | 9个 |
| 重复/冗余测试 | 10个 |
| 过时/无用测试 | 9个 |
| **合计** | **28个** |

---

## 四、操作命令

```bash
# 删除临时/诊断脚本
rm tests/check_div_balance.py
rm tests/check_env.py
rm tests/check_html_structure.py
rm tests/compare_tabs.py
rm tests/diagnose_news_cls.py
rm tests/diagnose_news_cls2.py
rm tests/final_check.py
rm tests/find_extra_div.py
rm tests/list_divs.py

# 删除重复/冗余测试
rm tests/test_cls_direct.py
rm tests/test_cls_once.py
rm tests/test_deepseek_analysis.py
rm tests/test_deepseek_combine_collection.py
rm tests/test_deepseek_combine_ztb_area.py
rm tests/test_deepseek_deepseek_analysis_event_driven.py
rm tests/test_deepseek_deepseek_analysis_news_cls.py
rm tests/test_deepseek_deepseek_analysis_news_combine.py
rm tests/test_deepseek_deepseek_analysis_news_ztb.py
rm tests/test_deepseek_deepseek_analysis_notice.py

# 删除过时/无用测试
rm tests/test_control_html.py
rm tests/test_decorators.py
rm tests/test_import_cls.py
rm tests/test_process_monitor.py
rm tests/test_redis_pool.py
rm tests/test_redis_write.py
rm tests/test_wencai_cookie_v2.py
rm tests/test_wrapper_v2.py
rm tests/test_zt_zb.py
```

---

## 五、Bak文件删除清单

| 文件 | 操作 |
|------|------|
| src/gs2026/monitor/monitor_bond.py.bak | 删除 |
| src/gs2026/monitor/monitor_bond.py.bak.2 | 删除 |
| src/gs2026/monitor/monitor_bond.py.bak.3 | 删除 |

**小计：3个**

---

**状态**: 🟡 待审核  
**审核后执行删除**
