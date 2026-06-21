"""清理4个分析文件中未使用的 browser_path 和 string_enum import"""
import os

files = [
    r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\deepseek\deepseek_analysis_news_cls.py',
    r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\deepseek\deepseek_analysis_news_combine.py',
    r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\deepseek\deepseek_analysis_news_ztb.py',
    r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\deepseek\deepseek_analysis_notice.py',
]

for filepath in files:
    with open(filepath, encoding='utf-8') as f:
        lines = f.readlines()
    
    new_lines = []
    removed = 0
    for line in lines:
        # Remove unused browser_path line
        if 'browser_path' in line and 'FIREFOX_PATH' in line:
            removed += 1
            continue
        new_lines.append(line)
    
    if removed > 0:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f'[OK] {os.path.basename(filepath)}: 移除 {removed} 行')
    else:
        print(f'[--] {os.path.basename(filepath)}: 无需修改')
