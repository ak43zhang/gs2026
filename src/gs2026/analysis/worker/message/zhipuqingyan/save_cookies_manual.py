"""
通过浏览器扩展或手动导出获取 Cookies 的辅助工具

如果你无法使用自动化工具获取 cookies，可以使用以下方法:

方法1: 浏览器控制台（推荐）
================================

1. 在 Edge 中打开智谱清言 (https://chatglm.cn)
2. 完成 Access Verification 验证
3. 按 F12 打开开发者工具
4. 切换到"控制台(Console)"标签
5. 粘贴以下代码并回车:

```javascript
// 复制这段代码到控制台
const cookies = await chrome.cookies.getAll({domain: ".chatglm.cn"});
console.log(JSON.stringify(cookies, null, 2));
```

或者使用这段代码:

```javascript
// 获取所有 cookies
const cookies = document.cookie.split(';').map(c => {
    const [name, ...valueParts] = c.trim().split('=');
    return {
        name: name,
        value: valueParts.join('='),
        domain: '.chatglm.cn',
        path: '/',
        expires: -1,
        httpOnly: false,
        secure: true,
        sameSite: 'Lax'
    };
});
console.log(JSON.stringify(cookies, null, 2));
```

6. 复制输出的 JSON
7. 粘贴到下面的输入框

方法2: 使用 EditThisCookie 扩展
================================

1. 安装 EditThisCookie 扩展
2. 访问智谱清言
3. 点击扩展图标
4. 选择"导出" → "导出为 JSON"
5. 复制 JSON

方法3: 直接编辑文件
================================

1. 创建文件: cookies/chatglm_cookies.json
2. 粘贴以下内容模板并修改:

[
  {
    "name": "你的cookie名称",
    "value": "你的cookie值",
    "domain": ".chatglm.cn",
    "path": "/",
    "expires": -1,
    "httpOnly": false,
    "secure": true,
    "sameSite": "Lax"
  }
]

"""

import json
from pathlib import Path

cookies_dir = Path(__file__).parent / 'cookies'
cookies_file = cookies_dir / 'chatglm_cookies.json'

def save_cookies_from_input():
    """从用户输入保存 cookies"""
    print("=" * 60)
    print("手动导入 Cookies")
    print("=" * 60)
    print()
    print("请从浏览器控制台复制 cookies JSON，然后粘贴到这里:")
    print("(输入完成后，输入 'END' 单独一行结束)")
    print()
    
    lines = []
    while True:
        line = input()
        if line.strip() == 'END':
            break
        lines.append(line)
    
    json_str = '\n'.join(lines)
    
    try:
        cookies = json.loads(json_str)
        
        if not isinstance(cookies, list):
            print("✗ 错误: cookies 必须是数组格式")
            return
        
        # 确保每个 cookie 有必要的字段
        for cookie in cookies:
            if 'domain' not in cookie:
                cookie['domain'] = '.chatglm.cn'
            if 'path' not in cookie:
                cookie['path'] = '/'
            if 'expires' not in cookie:
                cookie['expires'] = -1
            if 'httpOnly' not in cookie:
                cookie['httpOnly'] = False
            if 'secure' not in cookie:
                cookie['secure'] = True
            if 'sameSite' not in cookie:
                cookie['sameSite'] = 'Lax'
        
        # 保存
        cookies_dir.mkdir(exist_ok=True)
        with open(cookies_file, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        
        print()
        print(f"✓ 成功保存 {len(cookies)} 个 cookies")
        print(f"  文件: {cookies_file}")
        print()
        print("Cookies 列表:")
        for cookie in cookies:
            name = cookie.get('name', 'unknown')
            value = cookie.get('value', '')
            preview = value[:40] + '...' if len(value) > 40 else value
            print(f"  - {name}: {preview}")
        
    except json.JSONDecodeError as e:
        print(f"✗ JSON 格式错误: {e}")
        print("请确保复制的是有效的 JSON 格式")
    except Exception as e:
        print(f"✗ 错误: {e}")

def show_browser_guide():
    """显示浏览器操作指南"""
    print()
    print("=" * 60)
    print("浏览器操作指南")
    print("=" * 60)
    print()
    print("步骤1: 打开 Edge 浏览器")
    print("  开始菜单 → Microsoft Edge")
    print()
    print("步骤2: 访问智谱清言")
    print("  地址栏输入: https://chatglm.cn/main/alltoolsdetail?lang=zh")
    print()
    print("步骤3: 完成验证")
    print("  如果出现 Access Verification，请完成验证")
    print()
    print("步骤4: 打开开发者工具")
    print("  按 F12 键")
    print()
    print("步骤5: 切换到控制台")
    print("  点击 Console 标签")
    print()
    print("步骤6: 粘贴代码")
    print("  复制下面的代码，粘贴到控制台，按回车:")
    print()
    print("-" * 60)
    print('copy(document.cookie)')
    print("-" * 60)
    print()
    print("步骤7: 复制 cookies")
    print("  上面的命令已复制 cookies 到剪贴板")
    print("  或者使用:")
    print()
    print("-" * 60)
    print("""
const cookies = document.cookie.split(';').map(c => {
    const [name, ...valueParts] = c.trim().split('=');
    return {
        name: name,
        value: valueParts.join('='),
        domain: '.chatglm.cn',
        path: '/',
        expires: -1,
        httpOnly: false,
        secure: true,
        sameSite: 'Lax'
    };
});
console.log(JSON.stringify(cookies, null, 2));
copy(JSON.stringify(cookies, null, 2));
""")
    print("-" * 60)
    print()
    print("步骤8: 保存到文件")
    print(f"  将复制的 JSON 粘贴到: {cookies_file}")
    print()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'guide':
        show_browser_guide()
    else:
        save_cookies_from_input()
        input("\n按 Enter 键退出...")
