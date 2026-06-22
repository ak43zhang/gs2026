"""批量替换各页面的导航栏为 Jinja2 Include"""
import re
from pathlib import Path

TEMPLATE_DIR = Path("F:/pyworkspace2026/gs2026/src/gs2026/dashboard2/templates")

# 页面配置：(文件名, page_title, active_page)
PAGES = [
    ('collection.html', '数据采集', 'collection'),
    ('analysis.html', '数据分析', 'analysis'),
    ('analysis_center.html', '分析中心', 'ztb'),
    ('domain_analysis.html', '领域分析', 'analysis'),
    ('index.html', '', 'home'),
    ('news.html', '新闻管理', 'analysis'),
    ('notice_analysis.html', '公告分析', 'analysis'),
    ('notice_detail.html', '公告详情', 'analysis'),
    ('performance.html', '性能监控', 'performance'),
    ('profile.html', '个人中心', ''),
    ('reports.html', '报告中心', 'reports'),
    ('scheduler.html', '调度中心', 'scheduler'),
    ('stock_picker.html', '智能选股', 'picker'),
]

# 导航栏匹配模式（多种变体）
NAV_PATTERNS = [
    # 标准格式（带header）
    r'<header class="app-header">\s*<div class="header-left">\s*<div class="logo">.*?</div>\s*<span class="header-divider">.*?</span>\s*<span class="header-subtitle">.*?</span>\s*</div>\s*<nav class="main-nav">.*?<a href="/logout".*?</a>\s*</nav>\s*</header>',
    # collection.html 格式
    r'<header class="page-header">\s*<div class="header-left">\s*<div class="logo">.*?</div>\s*<span class="header-divider">.*?</span>\s*<span class="header-subtitle">.*?</span>\s*</div>\s*<nav class="main-nav">.*?<a href="/logout".*?</a>\s*</nav>\s*</header>',
]

def replace_nav(content, page_title, active_page):
    """替换导航栏为 include"""
    include_block = f'''<!-- 头部导航 -->
    {{% set page_title = '{page_title}' %}}
    {{% set active_page = '{active_page}' %}}
    {{% include 'nav.html' %}}'''
    
    for pattern in NAV_PATTERNS:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return content[:match.start()] + include_block + content[match.end():]
    return None

for filename, title, active in PAGES:
    filepath = TEMPLATE_DIR / filename
    if not filepath.exists():
        print(f"跳过: {filename} (不存在)")
        continue
    
    content = filepath.read_text(encoding='utf-8')
    new_content = replace_nav(content, title, active)
    
    if new_content:
        filepath.write_text(new_content, encoding='utf-8')
        print(f"✓ {filename}")
    else:
        print(f"✗ {filename} (未匹配到导航栏)")

print("\n完成！")
