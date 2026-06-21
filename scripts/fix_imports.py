"""批量更新旧import路径到新路径"""
import os
import re

# 定义替换映射
replacements = {
    'from gs2026.analysis.worker.message.deepseek.result_processor': 'from gs2026.analysis.worker.message.deepseek.processor.domain',
    'from gs2026.analysis.worker.message.deepseek.news_result_processor': 'from gs2026.analysis.worker.message.deepseek.processor.news',
    'from gs2026.analysis.worker.message.deepseek.proxy_pool': 'from gs2026.analysis.worker.message.deepseek.proxy.pool',
    'from gs2026.analysis.worker.message.deepseek.proxy_usage_logger': 'from gs2026.analysis.worker.message.deepseek.proxy.usage_logger',
    'from gs2026.analysis.worker.message.deepseek.deepseek_anti_block': 'from gs2026.analysis.worker.message.deepseek.browser.anti_block',
}

# 需要更新的文件列表
files = [
    r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\deepseek\deepseek_analysis_news_cls.py',
    r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\deepseek\deepseek_analysis_news_combine.py',
    r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\deepseek\deepseek_analysis_news_ztb.py',
    r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\deepseek\deepseek_analysis_notice.py',
    r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\deepseek\browser\anti_block.py',
    r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\deepseek\tools\migrate_analysis_news.py',
    r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\huoshanfangzhou\volcengine_analysis_event_driven.py',
    r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\huoshanfangzhou\volcengine_analysis_news_cls.py',
    r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\huoshanfangzhou\volcengine_analysis_news_combine.py',
    r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\huoshanfangzhou\volcengine_analysis_news_ztb.py',
    r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\huoshanfangzhou\volcengine_analysis_notice.py',
    r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\stepfun\analysis_event_driven.py',
    r'F:\pyworkspace2026\gs2026\src\verify_proxy_browser.py',
]

total_changes = 0
for filepath in files:
    if not os.path.exists(filepath):
        print(f'[SKIP] 文件不存在: {filepath}')
        continue
    
    with open(filepath, encoding='utf-8') as f:
        content = f.read()
    
    new_content = content
    changes = 0
    for old, new in replacements.items():
        if old in new_content:
            new_content = new_content.replace(old, new)
            changes += 1
    
    if changes > 0:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f'[OK] {os.path.basename(filepath)}: {changes} 处替换')
        total_changes += changes
    else:
        print(f'[--] {os.path.basename(filepath)}: 无需修改')

print(f'\n总计: {total_changes} 处替换')
