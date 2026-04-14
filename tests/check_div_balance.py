import re
content = open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard\templates\control.html', 'r', encoding='utf-8').read()

# 找到所有 div 标签位置
div_opens = [(m.start(), m.group()) for m in re.finditer(r'<div[^>]*>', content)]
div_closes = [(m.start(), m.group()) for m in re.finditer(r'</div>', content)]

print(f'总 <div 开始: {len(div_opens)}')
print(f'总 </div> 结束: {len(div_closes)}')

# 检查 tab-analysis 区域
analysis_start = content.find('id="tab-analysis"')
analysis_end = content.find('</div><!-- 关闭 tab-analysis -->') + len('</div><!-- 关闭 tab-analysis -->')
analysis_content = content[analysis_start:analysis_end]

analysis_opens = len(re.findall(r'<div[^>]*>', analysis_content))
analysis_closes = len(re.findall(r'</div>', analysis_content))

print(f'\ntab-analysis 区域:')
print(f'  <div 开始: {analysis_opens}')
print(f'  </div> 结束: {analysis_closes}')
print(f'  差值: {analysis_opens - analysis_closes}')