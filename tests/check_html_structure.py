content = open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard\templates\control.html', 'r', encoding='utf-8').read()

# 找到 tab-monitor 和 tab-analysis 之间的内容
monitor_start = content.find('id="tab-monitor"')
analysis_start = content.find('id="tab-analysis"')
analysis_end = content.find('</div><!-- 关闭 tab-analysis -->')

# 检查 tab-monitor 区域
tab_monitor_content = content[monitor_start:analysis_start]
print('tab-monitor 区域:')
print(f'  长度: {len(tab_monitor_content)}')
print(f'  div 开始数量: {tab_monitor_content.count("<div")}')
print(f'  div 结束数量: {tab_monitor_content.count("</div>")}')

# 检查 tab-analysis 区域  
tab_analysis_content = content[analysis_start:analysis_end+50]
print('\ntab-analysis 区域:')
print(f'  长度: {len(tab_analysis_content)}')
print(f'  div 开始数量: {tab_analysis_content.count("<div")}')
print(f'  div 结束数量: {tab_analysis_content.count("</div>")}')

# 检查整体
print('\n整体检查:')
print(f'  总 div 开始: {content.count("<div")}')
print(f'  总 div 结束: {content.count("</div>")}')
print(f'  差值: {content.count("<div") - content.count("</div>")}')