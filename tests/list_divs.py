content = open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard\templates\control.html', 'r', encoding='utf-8').read()

analysis_start = content.find('id="tab-analysis"')
analysis_end = content.find('</div><!-- 关闭 tab-analysis -->')
analysis_section = content[analysis_start:analysis_end]

lines = analysis_section.split('\n')
for i, line in enumerate(lines):
    if '<div' in line or '</div>' in line:
        print(f'{i+1}: {line.strip()[:60]}')