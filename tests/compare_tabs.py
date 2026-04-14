content = open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard\templates\control.html', 'r', encoding='utf-8').read()

# tab-monitor 区域
monitor_start = content.find('id="tab-monitor"')
analysis_start = content.find('id="tab-analysis"')
analysis_end = content.find('</div><!-- 关闭 tab-analysis -->')

monitor_section = content[monitor_start:analysis_start]
analysis_section = content[analysis_start:analysis_end+35]

print('tab-monitor:')
print(f'  opens: {monitor_section.count("<div")}')
print(f'  closes: {monitor_section.count("</div>")}')

print('tab-analysis:')
print(f'  opens: {analysis_section.count("<div")}')
print(f'  closes: {analysis_section.count("</div>")}')