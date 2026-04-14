content = open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard\templates\control.html', 'r', encoding='utf-8').read()
lines = content.split('\n')

# 找到所有包含 </div> 的行
print("所有 </div> 的位置:")
for i, line in enumerate(lines):
    if '</div>' in line:
        # 显示前后文
        context = line.strip()
        if len(context) > 80:
            context = context[:80] + '...'
        print(f"Line {i+1}: {context}")