#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import re

templates_dir = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates'

files = [f for f in os.listdir(templates_dir) if f.endswith('.html')]

for filename in files:
    filepath = os.path.join(templates_dir, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 替换所有 css 文件的版本号为 v=5
    new_content = re.sub(r"(\.css\S*)\?v=\d+", r"\1?v=5", content)
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f'✅ {filename} CSS版本升级到v=5')
    else:
        print(f'⏭️ {filename} 无需修改')

print('\n完成！')
