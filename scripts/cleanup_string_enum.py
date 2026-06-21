"""清理4个分析文件中未使用的 string_enum import"""
import os

files = [
    r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\deepseek\deepseek_analysis_news_cls.py',
    r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\deepseek\deepseek_analysis_news_combine.py',
    r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\deepseek\deepseek_analysis_news_ztb.py',
    r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\deepseek\deepseek_analysis_notice.py',
]

for filepath in files:
    with open(filepath, encoding='utf-8') as f:
        content = f.read()
    
    # Check if string_enum is used beyond the import line
    lines = content.split('\n')
    import_line_idx = None
    usage_count = 0
    for i, line in enumerate(lines):
        if 'string_enum' in line:
            if 'import' in line and 'from' in line:
                import_line_idx = i
            else:
                usage_count += 1
    
    if usage_count == 0 and import_line_idx is not None:
        # Remove string_enum from the import line
        line = lines[import_line_idx]
        # Pattern: from gs2026.utils import ..., string_enum, ...
        new_line = line.replace(', string_enum', '').replace('string_enum, ', '').replace('string_enum', '')
        if new_line.strip().endswith('import'):
            # If nothing left after import, remove entire line
            lines.pop(import_line_idx)
        else:
            lines[import_line_idx] = new_line
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        print(f'[OK] {os.path.basename(filepath)}: 移除 string_enum import')
    else:
        print(f'[--] {os.path.basename(filepath)}: string_enum 仍在使用({usage_count}处)')
