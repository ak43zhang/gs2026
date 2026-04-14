#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import re

templates_dir = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates'

# 定义替换规则
replacements = [
    ('href="/analysis-center"', 'href="/ztb-analysis"'),
    ('href="/news"', 'href="/news-analysis"'),
]

files = [
    'analysis.html',
    'analysis_center.html',
    'collection.html',
    'domain_analysis.html',
    'index.html',
    'monitor.html',
    'news.html',
    'notice_analysis.html',
    'performance.html',
    'reports.html',
    'scheduler.html',
]

for filename in files:
    filepath = os.path.join(templates_dir, filename)
    if not os.path.exists(filepath):
        print(f'跳过: {filename} (不存在)')
        continue
    
    # 读取文件（保持UTF-8编码）
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 应用替换
    modified = False
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            modified = True
            print(f'  {filename}: {old} -> {new}')
    
    # 写回文件
    if modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'✅ {filename} 已更新')
    else:
        print(f'⏭️ {filename} 无需修改')

print('\n完成！')
