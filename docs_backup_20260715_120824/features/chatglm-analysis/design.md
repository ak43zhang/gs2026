# 智谱清言版事件驱动分析 - 完整开发方案（已实施）

> **状态**: ✅ 已完成实施  
> **实施时间**: 2026-05-25  
> **代码位置**: `F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\zhipuqingyan\`

## 一、现状分析

### 1.1 DeepSeek 版本核心流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    DeepSeek 事件驱动分析流程                        │
├─────────────────────────────────────────────────────────────────┤
│  1. 查询待分析记录 (news_area 表)                                 │
│  2. 获取板块/概念字典 (data_industry_code_ths, ths_gn_names_rq)  │
│  3. 构造多维度评分 Prompt (重要程度 + 业务影响 + 综合评分)          │
│  4. 分布式账号池获取可用账号                                        │
│  5. Playwright 启动 Firefox 浏览器                                │
│  6. 访问 https://chat.deepseek.com/                               │
│  7. 登录 (用户名/密码)                                            │
│  8. 启用 DeepThink 模式 + 联网搜索                                 │
│  9. 发送 Prompt 并等待回复                                         │
│  10. 解析 JSON 结果                                                │
│  11. 存储到 analysis_area2026 表                                   │
│  12. 拆分入库到 analysis_domain_detail_2026 表                     │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 DeepSeek 版本技术栈

| 组件 | 技术 |
|------|------|
| 浏览器自动化 | Playwright + Firefox |
| 账号管理 | DistributedAccountPool (MySQL) |
| 分布式锁 | Redis |
| 数据存储 | MySQL + SQLAlchemy |
| 重试机制 | @db_retry 装饰器 |
| 任务调度 | run_daemon_task |

### 1.3 智谱清言页面结构分析

```
URL: https://chatglm.cn/main/alltoolsdetail?lang=zh

页面元素:
├── 输入框: textarea (placeholder="和我聊聊天吧")
├── 功能按钮（输入框上方）:
│   ├── 思考 (DeepThink 类似功能)
│   ├── 联网 (联网搜索)
│   ├── Agent
│   ├── 研究模式
│   ├── PPT模式
│   └── 数据分析
├── 发送机制: 回车或点击发送按钮
├── 回复区域: 动态生成的 markdown 内容
└── 弹窗: 产品推广弹窗（需处理）
```

**关键差异**:
1. ✅ 无需登录即可使用
2. 需要先点击"思考"和"联网"按钮启用功能
3. 需要处理产品推广弹窗
4. 回复格式可能与 DeepSeek 不同

---

## 二、开发方案

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    智谱清言版事件驱动分析                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   主入口      │───▶│  任务调度器   │───▶│  工作进程     │      │
│  │ chatglm_ai   │    │  area_ai     │    │  chatglm_ai  │      │
│  └──────────────┘    └──────────────┘    └──────┬───────┘      │
│                                                   │               │
│  ┌────────────────────────────────────────────────┘               │
│  │                                                               │
│  ▼                                                               │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    核心分析流程                              │  │
│  ├─────────────────────────────────────────────────────────────┤  │
│  │  1. 查询待分析记录 (news_area 表)                           │  │
│  │  2. 获取板块/概念字典                                        │  │
│  │  3. 构造 Prompt (复用 DeepSeek 版本)                          │  │
│  │  4. 【可选】分布式账号池获取账号（预留扩展）                   │  │
│  │  5. Playwright 启动 Firefox/Chrome                           │  │
│  │  6. 访问 https://chatglm.cn/main/alltoolsdetail              │  │
│  │  7. 【预留】登录流程（默认跳过）                              │  │
│  │  8. 关闭产品推广弹窗                                          │  │
│  │  9. 点击"思考"按钮启用深度思考                                 │  │
│  │  10. 点击"联网"按钮启用联网搜索                               │  │
│  │  11. 发送 Prompt 并等待回复                                  │  │
│  │  12. 解析 JSON 结果                                          │  │
│  │  13. 存储到 analysis_area_chatglm_2026 表                   │  │
│  │  14. 拆分入库到 analysis_domain_detail_chatglm_2026 表        │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐         │
│  │   账号池      │    │   Redis      │    │   MySQL      │         │
│  │  (预留扩展)  │    │  分布式锁    │    │  数据存储    │         │
│  └──────────────┘    └──────────────┘    └──────────────┘         │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 文件结构

```
gs2026/
└── analysis/
    └── worker/
        └── message/
            ├── deepseek/                    # 已有 DeepSeek 版本
            │   ├── deepseek_analysis_event_driven.py
            │   └── result_processor.py
            │
            └── chatglm/                     # 新增智谱清言版本
                ├── __init__.py
                ├── chatglm_analysis_event_driven.py    # 主入口
                ├── chatglm_browser.py                   # 浏览器操作封装
                ├── chatglm_login.py                     # 登录流程（预留扩展）
                ├── chatglm_prompt.py                    # Prompt 构造
                └── result_processor.py                  # 结果解析入库
```

### 2.3 核心模块设计

#### 2.3.1 chatglm_analysis_event_driven.py

**功能**: 主入口，复用 DeepSeek 版本的整体流程

**主要改动**:
1. 替换 `deepseek_analysis()` 为 `chatglm_analysis()`
2. 移除账号池依赖（默认不登录，预留扩展接口）
3. 替换表名 `analysis_area_chatglm_2026`
4. 复用 Redis 分布式锁、重试机制、任务调度

```python
"""智谱清言事件驱动分析主入口"""

# 复用 DeepSeek 版本的基础配置
# ... (省略导入语句)

def chatglm_ai(
    query_list: List[Tuple[str, str, str]],
    bk_dic_str: str,
    gn_dic_str: str,
    table_name: str,
    analysis_table_name: str,
    _headless: bool
) -> None:
    """对指定的领域-日期组合列表执行智谱清言 AI 分析。"""
    start = time.time()

    for i in query_list:
        t_date: str = i[0]
        main_area: str = i[1]
        child_area: str = i[2]

        # 构造 Prompt（复用 DeepSeek 版本）
        query = build_prompt(t_date, main_area, child_area, bk_dic_str, gn_dic_str)
        query = string_util.sensitive_word_replacement(query)
        print(query)

        # 调用智谱清言获取 AI 分析结果
        analysis: str = chatglm_analysis(query, _headless)

        # 清理返回结果中的非 JSON 前缀和注释
        analysis = string_util.remove_json_prefix(analysis, 'json')
        analysis = string_util.remove_json_prefix(analysis, 'Copy')
        analysis = string_util.remove_json_prefix(analysis, 'Code')
        analysis = string_util.remove_json_comments(analysis)
        analysis = analysis.lstrip()

        # 从字符串中提取合法的 JSON 数据
        json_data, remaining_text = string_util.extract_json_from_string(analysis)

        if string_util.is_valid_json(json_data) and json_data != '{}':
            # JSON 合法且非空，插入分析结果到数据库
            update_sql = f"INSERT INTO {analysis_table_name} (news_date,main_area,child_area,json_data) VALUES ('{t_date}','{main_area}','{child_area}','{json_data}')"
            mysql_tool.update_data(update_sql)
            
            # 拆分入库到新表
            try:
                stats = process_domain(json_data, main_area, child_area, t_date, version='chatglm-1.0.0')
                logger.info(f"领域分析拆分入库: {stats}")
            except Exception as e:
                logger.error(f"领域分析拆分入库失败: {e}")
        else:
            logger.error(table_name + "该数据ai分析失败，请重试")

    end = time.time()
    execution_time: float = end - start
    logger.info(f"{table_name}智谱清言AI分析耗时: {execution_time} 秒")


def area_ai_analysis(
    table_name: str,
    analysis_table_name: str,
    start_date: str,
    _headless: bool
) -> bool | None:
    """从数据库获取待分析记录，使用 Redis 分布式锁进行单条分析。"""
    # 查询尚未分析的候选记录
    sql = f"""
        select SQL_NO_CACHE '{start_date}' as t_date,
               {table_name}.main_area,
               {table_name}.child_area
        from {table_name}
        left join (select * from {analysis_table_name} where news_date='{start_date}') as analysis_area2
            on {table_name}.child_area = analysis_area2.child_area
        where is_use='1' and analysis_area2.news_date is null
        order by rand()
        limit 10
    """
    bk_dic_sql: str = "select name from data_industry_code_ths"
    gn_dic_sql: str = "select name from ths_gn_names_rq where flag='1'"

    with engine.connect() as conn:
        candidates: List[dict] = pd.read_sql(sql, con=conn).to_dict('records')
        if not candidates:
            return False

        bk_dic_str: str = ','.join(pd.read_sql(bk_dic_sql, conn)['name'].astype(str))
        gn_dic_str: str = ','.join(pd.read_sql(gn_dic_sql, conn)['name'].astype(str))

    # 遍历候选记录，尝试获取 Redis 分布式锁
    for cand in candidates:
        t_date: str = cand['t_date']
        main_area: str = cand['main_area']
        child_area: str = cand['child_area']

        lock_key: str = f"area_ai_lock:chatglm:{table_name}:{t_date}:{main_area}:{child_area}"
        lock = redis_client.lock(lock_key, timeout=900, blocking_timeout=0)

        if lock.acquire(blocking=False):
            try:
                # 成功获取锁，执行 AI 分析
                chatglm_ai([(t_date, main_area, child_area)], bk_dic_str, gn_dic_str, table_name, analysis_table_name, _headless)
                return True
            except Exception as e:
                logger.error(f"处理记录 {t_date} {main_area} {child_area} 失败: {e}")
            finally:
                try:
                    lock.release()
                except redis.exceptions.LockNotOwnedError:
                    pass

    return True


def area_ai(area_ai_date: str, polling_time: int) -> None:
    """对指定日期执行领域 AI 分析的轮询循环。"""
    flag: bool = True
    year: str = area_ai_date[0:4]
    table: str = "news_area"
    analysis_table: str = f"analysis_area_chatglm_{year}"

    while flag:
        flag = area_ai_analysis(table, analysis_table, area_ai_date, True)
        time.sleep(polling_time)


def analysis_event_driven(date_list_: List[str]) -> None:
    """事件驱动分析主入口，按日期列表依次执行全领域 AI 分析。"""
    for area_date in date_list_:
        logger.info('=============================' + area_date + '=============================')
        area_ai(area_date, 1)


if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description='智谱清言领域事件分析')
    parser.add_argument('--params', type=str, help='JSON格式的参数')
    args = parser.parse_args()
    
    date_list = ['2026-04-26','2026-04-27','2026-04-28','2026-04-29','2026-04-30',
                 '2026-05-01','2026-05-02','2026-05-03','2026-05-04','2026-05-05','2026-05-06','2026-05-07','2026-05-08','2026-05-09','2026-05-10']
    
    if args.params:
        try:
            params = json.loads(args.params)
            if 'date_list' in params:
                date_list = params['date_list']
                logger.info(f'从参数获取日期列表: {date_list}')
        except json.JSONDecodeError as e:
            logger.error(f'参数解析失败: {e}')
    
    run_daemon_task(target=analysis_event_driven, args=(date_list,))
```

#### 2.3.2 chatglm_browser.py

**功能**: 封装智谱清言网页操作

```python
"""智谱清言浏览器操作封装"""

import re
import time
import random
from typing import Optional
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from gs2026.utils import log_util, display_config, string_util
from gs2026.utils.config_util import get_config

logger = log_util.setup_logger(__name__)

# 浏览器配置
BROWSER_PATH: str = get_config("common.browser_path", r"C:\Program Files\Mozilla Firefox\firefox.exe")
PAGE_TIMEOUT: int = 900000  # 15分钟


class ChatGLMBrowser:
    """智谱清言浏览器操作类"""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser = None
        self.page = None
        self.playwright = None
        
    def launch(self) -> None:
        """启动浏览器"""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.firefox.launch(
            headless=self.headless, 
            executable_path=BROWSER_PATH
        )
        self.page = display_config.set_page_display_options_chrome(self.browser)
        logger.info("浏览器启动成功")
        
    def navigate(self) -> None:
        """访问智谱清言页面"""
        self.page.goto('https://chatglm.cn/main/alltoolsdetail?lang=zh', timeout=PAGE_TIMEOUT)
        logger.info("页面加载完成")
        
    def close_popup(self) -> None:
        """关闭产品推广弹窗"""
        try:
            # 尝试多种方式关闭弹窗
            # 1. 点击"我知道了"按钮
            try:
                self.page.click('button:has-text("我知道了")', timeout=3000)
                logger.info("关闭弹窗: 我知道了")
                return
            except:
                pass
                
            # 2. 点击关闭按钮
            try:
                self.page.click('button[class*="close"], [class*="close"] button', timeout=3000)
                logger.info("关闭弹窗: 关闭按钮")
                return
            except:
                pass
                
            # 3. 按 ESC 键
            self.page.press('body', 'Escape')
            logger.info("关闭弹窗: ESC键")
            
        except Exception as e:
            logger.warning(f"关闭弹窗失败或无需关闭: {e}")
            
    def enable_thinking(self) -> None:
        """启用思考模式（深度思考）"""
        try:
            # 点击"思考"按钮
            self.page.get_by_text('思考', exact=False).click()
            logger.info("启用思考模式")
        except Exception as e:
            logger.error(f"启用思考模式失败: {e}")
            raise
            
    def enable_web_search(self) -> None:
        """启用联网搜索功能"""
        try:
            # 点击"联网"按钮
            self.page.get_by_text('联网', exact=False).click()
            logger.info("启用联网搜索")
        except Exception as e:
            logger.error(f"启用联网搜索失败: {e}")
            raise
            
    def send_message(self, query: str) -> None:
        """发送消息"""
        try:
            # 1. 找到输入框并填充
            textarea = self.page.locator('textarea[placeholder*="聊天"], textarea')
            textarea.fill(query)
            
            # 2. 触发输入事件
            self.page.evaluate('''() => {
                const textarea = document.querySelector('textarea');
                if (textarea) {
                    textarea.dispatchEvent(new Event('input', { bubbles: true }));
                    textarea.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }''')
            
            # 3. 随机短暂等待
            time.sleep(random.randint(1, 2))
            
            # 4. 发送（优先回车，备选点击发送按钮）
            try:
                textarea.press('Enter')
            except:
                # 备选：点击发送按钮
                self.page.click('button[type="submit"], button:has-text("发送"), [class*="send"]')
                
            logger.info("消息已发送")
            
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            raise
            
    def wait_for_response(self) -> str:
        """等待并获取回复"""
        try:
            # 等待回复区域出现（多种选择器尝试）
            selectors = [
                '.markdown-body',
                '.chat-content',
                '[class*="message"]',
                '[class*="response"]',
                'div[class*="markdown"]'
            ]
            
            response_text = ''
            for selector in selectors:
                try:
                    self.page.wait_for_selector(selector, timeout=PAGE_TIMEOUT)
                    response_text = self.page.inner_text(selector)
                    if response_text:
                        logger.info(f"获取回复成功，选择器: {selector}")
                        break
                except:
                    continue
                    
            if not response_text:
                raise Exception("无法获取回复内容")
                
            return response_text
            
        except Exception as e:
            logger.error(f"等待回复失败: {e}")
            raise
            
    def close(self) -> None:
        """关闭浏览器"""
        try:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            logger.info("浏览器已关闭")
        except Exception as e:
            logger.error(f"关闭浏览器失败: {e}")


def chatglm_analysis(query: str, _headless: bool = True) -> str:
    """通过智谱清言获取 AI 分析结果。
    
    流程:
    1. 启动浏览器
    2. 访问智谱清言页面
    3. 关闭弹窗
    4. 启用思考和联网功能
    5. 发送 Prompt
    6. 等待并获取回复
    7. 关闭浏览器
    
    Args:
        query: 发送给智谱清言的分析 prompt
        _headless: 是否以无头模式运行
        
    Returns:
        智谱清言返回的 AI 分析结果字符串
    """
    logger.info(f"开始智谱清言分析，query长度: {len(query)}")
    
    browser = ChatGLMBrowser(headless=_headless)
    
    try:
        # 1. 启动浏览器
        browser.launch()
        
        # 2. 访问页面
        browser.navigate()
        
        # 3. 关闭弹窗
        browser.close_popup()
        
        # 4. 启用思考模式
        browser.enable_thinking()
        
        # 5. 启用联网搜索
        browser.enable_web_search()
        
        # 6. 发送消息
        browser.send_message(query)
        
        # 7. 等待并获取回复
        result = browser.wait_for_response()
        
        # 8. 清理结果
        result = string_util.remove_citation(result).replace("'", "(").replace("\u2019", "）").replace("'", "")
        
        logger.info(f"智谱清言分析完成，结果长度: {len(result)}")
        return result
        
    except Exception as e:
        logger.error(f"智谱清言分析失败: {e}")
        return '{}'
        
    finally:
        browser.close()
```

#### 2.3.3 chatglm_login.py

**功能**: 登录流程（预留扩展，默认不执行）

```python
"""智谱清言登录流程 - 预留扩展接口

当前版本：无需登录即可使用
未来扩展：如需登录，在此实现
"""

from typing import Optional
from playwright.sync_api import Page


def chatglm_login(page: Page, username: Optional[str] = None, password: Optional[str] = None) -> bool:
    """智谱清言登录流程（预留扩展接口）
    
    当前版本无需登录，此函数预留用于未来扩展。
    
    Args:
        page: Playwright 页面对象
        username: 用户名/手机号（可选）
        password: 密码/验证码（可选）
        
    Returns:
        bool: 是否登录成功
    """
    # 当前版本：无需登录，直接返回成功
    if not username or not password:
        return True
        
    # 预留：未来如需登录，在此实现
    # 1. 检查是否需要登录
    # 2. 点击登录按钮
    # 3. 填写用户名/密码
    # 4. 处理验证码（如有）
    # 5. 点击登录
    # 6. 等待登录完成
    
    return True


def check_login_status(page: Page) -> bool:
    """检查登录状态（预留扩展）
    
    Args:
        page: Playwright 页面对象
        
    Returns:
        bool: 是否已登录
    """
    # 当前版本：默认未登录也可使用
    return True
```

#### 2.3.4 chatglm_prompt.py

**功能**: 构造 Prompt（**完全复用 DeepSeek 版本**）

```python
"""智谱清言 Prompt 构造 - 完全复用 DeepSeek 版本"""

from gs2026.utils import string_util


def build_prompt(t_date: str, main_area: str, child_area: str, 
                 bk_dic_str: str, gn_dic_str: str) -> str:
    """构造智谱清言分析 Prompt
    
    完全复用 DeepSeek 版本的 Prompt 模板，包含：
    - 重要程度评分（权威性与级别、新颖性与想象力、相关性与纯度）
    - 业务影响维度评分（12个经营维度）
    - 综合评分计算
    - 利空利好判断
    - 消息大小分级
    - 涉及板块和概念
    - 股票代码分析
    - 原因分析和深度分析
    
    Args:
        t_date: 分析日期
        main_area: 主领域
        child_area: 子领域
        bk_dic_str: 板块字典字符串
        gn_dic_str: 概念字典字符串
        
    Returns:
        构造好的 Prompt 字符串
    """
    query = f"{t_date}全球重要大事件集锦，按重要程度给出30条主领域为{main_area}，子领域为{child_area}的消息，" + """
重要程度评分：按照 权威性与级别 角度评估程度分为 国家级政策（5分）、部委/地方政策（4分）、行业会议（3分）、公司公告（2分）、市场传闻（1分）。按照 新颖性与想象力 角度评估程度分为 新技术/新政策（5分）、现有产业数据向好（3分）。按照 相关性与纯度 角度评估程度分为 直接受益（核心业务高度相关）（5分）、间接受益（产业链上下游）（3分）、情绪相关（概念沾边）（1分），最终由三者分数相加，总分范围0至15分。
业务影响维度评分：（每个维度-5至5分，总分范围-60至60）
    从12个关键经营维度评估消息的实质性影响，正面影响为正分，负面影响为负分，无影响为0分。评分时需结合消息内容具体分析。
    按照 成本控制 维度评估程度分为	显著降低成本（5）、一定程度降低成本（3）、略有影响（1）	显著提高成本（-5）、一定程度提高（-3）、略有提高（-1），
    按照 运营效率 维度评估程度分为	大幅提升效率（5）、有所提升（3）、轻微提升（1）	大幅降低效率（-5）、有所降低（-3）、轻微降低（-1），
    按照 资金与财务 维度评估程度分为	极大改善现金流/利润（5）、明显改善（3）、略有改善（1）	极大恶化（-5）、明显恶化（-3）、略有恶化（-1），
    按照 技术或工艺突破 维度评估程度分为	重大突破（5）、明显进步（3）、小幅改进（1）	技术落后（-5）、竞争力下降（-3）、小幅退步（-1），
    按照 产品定价权 维度评估程度分为	显著增强定价能力（5）、有所增强（3）、轻微增强（1）	显著削弱（-5）、有所削弱（-3）、轻微削弱（-1），
    按照 市场份额扩张 维度评估程度分为	大幅提升市占率（5）、明显提升（3）、小幅提升（1）	大幅下降（-5）、明显下降（-3）、小幅下降（-1），
    按照 产业链地位 维度评估程度分为	大幅提升话语权（5）、有所提升（3）、轻微提升（1）	大幅降低（-5）、有所降低（-3）、轻微降低（-1），
    按照 产品结构升级 维度评估程度分为	推动高端化/高附加值（5）、明显优化（3）、小幅调整（1）	导致低端化（-5）、明显劣化（-3）、小幅劣化（-1），
    按照 成功拓展新业务 维度评估程度分为	开辟全新业务领域（5）、进入新市场（3）、尝试新方向（1）	退出核心业务（-5）、收缩业务（-3）、暂停拓展（-1），
    按照 政策支持 维度评估程度分为	获得强力政策扶持（5）、一般性支持（3）、间接利好（1）	遭遇政策打压（-5）、限制（-3）、间接利空（-1），
    按照 行业趋势红利 维度评估程度分为	处于爆发风口（5）、明显受益（3）、略有受益（1）	逆势而行（-5）、明显受损（-3）、略有受损（-1），
    按照 输入成本下降 维度评估程度分为	大幅降低原材料/能源成本（5）、明显降低（3）、小幅降低（1）	大幅上升（-5）、明显上升（-3）、小幅上升（-1），
    最终综合分析算出。
综合评分：（通过重要程度评分×4+业务影响维度评分）。
利空利好（由业务影响维度评分和综合评分分析得出，业务影响维度评分为负则为利空，综合评分小于0则为利空，0-60则为中性，大于60则为利好，字典值有利好、利空、中性三个字典值）。
消息大小（由综合评分计算得出，重大：90 ≤ 综合评分，大：60 ≤ 综合评分 < 90，中：30 ≤ 综合评分 < 60，小：综合评分 < 30,字典值有重大，大，中，小四个）。
涉及板块（板块字典："""+bk_dic_str+"""，以英文逗号分隔）。
涉及概念（概念字典："""+gn_dic_str+"""，以英文逗号分隔）。
股票代码（请根据成本控制、运营效率、资金与财务、技术或工艺突破、产品定价权、市场份额扩张、产业链地位、产品结构升级、成功拓展新业务、政策支持、行业趋势红利、输入成本下降等多个维度分析该消息直接受益或者受损的a股沪深板块股票代码，多值按照英文逗号分隔，6位代码），
时间（事件发表最早的时间，时间格式为yyyy-MM-dd HH:mm:ss），
事件来源（事件最早时间的来源）
原因分析（该字段主要根据成本控制、运营效率、资金与财务、技术或工艺突破、产品定价权、市场份额扩张、产业链地位、产品结构升级、成功拓展新业务、政策支持、行业趋势红利、输入成本下降等多个维度分析该消息对a股具体股票代码直接受益或者受损的原因）,
深度分析：(是根据成本控制、运营效率、资金与财务、技术或工艺突破、产品定价权、市场份额扩张、产业链地位、产品结构升级、成功拓展新业务、政策支持、行业趋势红利、输入成本下降等多个维度分析该消息的实质性影响,深度分析结果按照前面的维度+详细分析原因+维度评估程度分组成)
返回结果为json对象，json 结构为       
{"消息集合": [
    "主领域": "",
    "子领域": "",
    "时间":"",
    "事件来源":"",
    "关键事件": "",
    "简要描述": "",
    "利空利好":"",
    "消息大小":"",
    "涉及板块": "",
    "涉及概念": "",
    "股票代码": "",
    "原因分析":"",
    "重要程度评分":"",
    "业务影响维度评分":"",
    "综合评分":"",
    "深度分析":[""]
]}  
请返回json结果。
"""
    return query
```

#### 2.3.5 result_processor.py

**功能**: 结果解析和入库（**复用 DeepSeek 版本，修改表名**）

```python
"""智谱清言分析结果解析和入库 - 复用 DeepSeek 版本"""

import json
import logging
from typing import Dict, Any
from gs2026.utils import mysql_util, config_util

logger = logging.getLogger(__name__)

# 复用 DeepSeek 版本的 process_domain 函数
# 只需修改表名前缀

# 从 DeepSeek 版本复制 result_processor.py 内容
# 修改 INSERT 语句中的表名：
# analysis_domain_detail_2026 -> analysis_domain_detail_chatglm_2026

# 具体实现参考 DeepSeek 版本的 result_processor.py
```

### 2.4 数据库设计

#### 2.4.1 复用 DeepSeek 版本表结构

> **重要**: 智谱清言版本**完全复用** DeepSeek 版本的数据库表，无需新建表。

**共用表名**:
- `analysis_area2026` - 分析结果主表
- `analysis_domain_detail_2026` - 分析明细表

**数据区分方式**:
通过 `analysis_version` 字段区分数据来源：
- DeepSeek: `1.0.0` 或 `deepseek-x.x.x`
- 智谱清言: `zhipuqingyan-1.0.0`

**查询示例**:
```sql
-- 查询所有分析结果（包含DeepSeek和智谱清言）
SELECT * FROM analysis_domain_detail_2026;

-- 查询智谱清言分析结果
SELECT * FROM analysis_domain_detail_2026 
WHERE analysis_version LIKE 'zhipuqingyan%';

-- 查询DeepSeek分析结果
SELECT * FROM analysis_domain_detail_2026 
WHERE analysis_version LIKE 'deepseek%' OR analysis_version = '1.0.0';
```

**表结构参考**（与DeepSeek版本相同）:
```sql
-- 分析结果主表
CREATE TABLE IF NOT EXISTS analysis_area2026 (
    id INT AUTO_INCREMENT PRIMARY KEY,
    news_date VARCHAR(10) COMMENT '分析日期',
    main_area VARCHAR(50) COMMENT '主领域',
    child_area VARCHAR(50) COMMENT '子领域',
    json_data JSON COMMENT 'AI分析结果JSON',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_date (news_date),
    INDEX idx_area (main_area, child_area)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 分析明细表
CREATE TABLE IF NOT EXISTS analysis_domain_detail_2026 (
    id INT AUTO_INCREMENT PRIMARY KEY,
    content_hash VARCHAR(32) UNIQUE COMMENT '内容哈希',
    main_area VARCHAR(50) COMMENT '主领域',
    child_area VARCHAR(50) COMMENT '子领域',
    event_time DATETIME COMMENT '事件时间',
    event_source VARCHAR(200) COMMENT '事件来源',
    key_event VARCHAR(500) COMMENT '关键事件',
    brief_desc VARCHAR(1000) COMMENT '简要描述',
    importance_score INT COMMENT '重要程度评分',
    business_impact_score INT COMMENT '业务影响评分',
    composite_score INT COMMENT '综合评分',
    news_size VARCHAR(10) COMMENT '消息大小',
    news_type VARCHAR(10) COMMENT '利空利好',
    sectors JSON COMMENT '涉及板块',
    concepts JSON COMMENT '涉及概念',
    stock_codes JSON COMMENT '股票代码',
    reason_analysis TEXT COMMENT '原因分析',
    deep_analysis JSON COMMENT '深度分析',
    analysis_version VARCHAR(20) COMMENT '版本',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_hash (content_hash),
    INDEX idx_date (event_time),
    INDEX idx_area (main_area, child_area),
    INDEX idx_sentiment (news_type),
    INDEX idx_score (composite_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 2.5 复用清单

| 组件 | DeepSeek 版本 | 智谱清言版本 | 复用方式 |
|------|--------------|-------------|---------|
| 主入口流程 | `analysis_event_driven()` | `chatglm_analysis_event_driven()` | 复制修改 |
| Prompt 构造 | `build_prompt()` | `build_prompt()` | **完全复用** |
| 结果解析 | `result_processor.py` | `result_processor.py` | **完全复用**（改表名） |
| 账号池 | `DistributedAccountPool` | 预留扩展接口 | **移除依赖** |
| Redis 锁 | `redis_client.lock()` | `redis_client.lock()` | **完全复用** |
| 重试机制 | `@db_retry` | `@db_retry` | **完全复用** |
| 任务调度 | `run_daemon_task` | `run_daemon_task` | **完全复用** |
| 浏览器配置 | `display_config` | `display_config` | **完全复用** |
| 字符串工具 | `string_util` | `string_util` | **完全复用** |
| 数据库工具 | `mysql_tool` | `mysql_tool` | **完全复用** |
| 日志工具 | `logger` | `logger` | **完全复用** |
| 邮件告警 | `email_util` | `email_util` | **完全复用** |
| 浏览器操作 | `deepseek_analysis()` | `chatglm_analysis()` | **重新实现** |
| 登录流程 | DeepSeek 登录 | 预留扩展接口 | **默认跳过** |
| 弹窗处理 | 无 | `close_popup()` | **新增** |
| 功能启用 | DeepThink+Search | 思考+联网 | **重新实现** |

### 2.6 开发步骤

#### Phase 1: 基础框架 (2天)
1. 创建目录结构 `analysis/worker/message/chatglm/`
2. 复制 `result_processor.py`（修改表名）
3. 创建 `chatglm_prompt.py`（复用 Prompt）
4. 创建 `chatglm_login.py`（预留扩展接口）
5. 创建 `chatglm_browser.py`（核心开发）

#### Phase 2: 核心功能 (3天)
1. 实现 `chatglm_browser.py` 基础操作
2. 实现弹窗关闭逻辑
3. 实现"思考"和"联网"按钮点击
4. 实现消息发送和回复获取
5. 实现 `chatglm_analysis()` 函数
6. 实现 `chatglm_analysis_event_driven.py` 主入口

#### Phase 3: 集成测试 (2天)
1. 单条记录测试
2. 批量记录测试
3. 异常处理测试（弹窗、超时、JSON解析等）
4. 数据正确性验证

#### Phase 4: 优化部署 (1天)
1. 添加监控和告警
2. 性能优化（并发、超时等）
3. 文档完善
4. 正式上线

### 2.7 风险与应对

| 风险 | 可能性 | 应对措施 |
|------|--------|---------|
| 页面结构变化 | 中 | 使用多种选择器备选，添加容错机制 |
| 产品推广弹窗变化 | 中 | 支持多种关闭方式（按钮、ESC、点击外部） |
| 反爬虫检测 | 中 | 添加随机延迟、User-Agent轮换 |
| 回复格式不一致 | 中 | 增强 JSON 解析容错能力 |
| "思考"/"联网"按钮位置变化 | 中 | 使用文本匹配而非位置匹配 |
| 免费额度限制 | 低 | 监控调用频率，必要时添加延时 |

### 2.8 与 DeepSeek 版本对比

| 特性 | DeepSeek | 智谱清言 |
|------|----------|---------|
| 登录 | 需要 | **无需** |
| 浏览器 | Firefox | Firefox/Chrome |
| 深度思考 | DeepThink 按钮 | "思考" 按钮 |
| 联网搜索 | Search 按钮 | "联网" 按钮 |
| 弹窗处理 | 无 | **需要处理** |
| 账号池 | 必需 | **预留扩展** |
| 分布式锁 | Redis | Redis（复用） |
| 重试机制 | 30次 | 30次（复用） |
| Prompt | 多维度评分 | **完全复用** |
| 结果存储 | MySQL | MySQL（复用） |

---

## 三、关键代码差异

### 3.1 核心流程差异

```python
# DeepSeek 版本
def deepseek_analysis(query, _headless):
    # 1. 获取账号
    with pool.account() as account_info:
        # 2. 登录
        login(page, account_info['username'], account_info['password'])
        # 3. 启用 DeepThink + Search
        page.get_by_role("button", name=re.compile(r"DeepThink", re.IGNORECASE)).click()
        page.get_by_role("button", name=re.compile(r"Search", re.IGNORECASE)).click()
        # 4. 发送消息
        # 5. 获取回复

# 智谱清言版本
def chatglm_analysis(query, _headless):
    # 1. 【无】获取账号（默认不登录）
    # 2. 【无】登录流程（默认跳过）
    # 3. 关闭弹窗
    browser.close_popup()
    # 4. 启用 思考 + 联网
    browser.enable_thinking()
    browser.enable_web_search()
    # 5. 发送消息
    # 6. 获取回复
```

### 3.2 浏览器操作差异

```python
# DeepSeek: 使用 get_by_role 定位按钮
page.get_by_role("button", name=re.compile(r"DeepThink", re.IGNORECASE)).click()
page.get_by_placeholder("Message DeepSeek").fill(query)

# 智谱清言: 使用文本匹配定位按钮
page.get_by_text('思考', exact=False).click()
page.get_by_text('联网', exact=False).click()
page.locator('textarea').fill(query)
```

---

## 四、总结

### 4.1 核心思路

**最大化复用 DeepSeek 版本的成果**：
- ✅ **完全复用**: Prompt 构造、结果解析、Redis锁、重试机制、任务调度、基础设施
- 🔄 **重新实现**: 浏览器操作（页面交互、弹窗处理、功能启用）
- ➕ **新增**: 弹窗关闭逻辑、预留登录扩展接口
- ➖ **移除**: 账号池依赖（默认不登录）

### 4.2 预期工作量

- **总开发时间**: 约 7-8 天
- **代码复用率**: 约 80%（Prompt、结果处理、基础设施）
- **新增代码**: 约 20%（浏览器操作适配、弹窗处理）

### 4.3 下一步行动

1. **开发阶段**: 按 Phase 1-4 逐步实施
2. **测试阶段**: 单条→批量→异常→上线
3. **优化阶段**: 监控、性能调优

---

**请审核此方案，确认后我将开始实施。**
