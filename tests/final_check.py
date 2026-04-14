content = open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard\templates\control.html', 'r', encoding='utf-8').read()

# 整体检查
print(f'总 <div: {content.count("<div")}')
print(f'总 </div>: {content.count("</div>")}')

# 检查 body 内
body_start = content.find('<body>')
body_end = content.find('</body>')
body = content[body_start:body_end]
print(f'\nBody 内 <div: {body.count("<div")}')
print(f'Body 内 </div>: {body.count("</div>")}')