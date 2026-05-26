# 使用 Microsoft Edge 获取 Cookies 完整流程

## 步骤1: 打开 Edge 并访问智谱清言

1. 打开 **Microsoft Edge** 浏览器
2. 访问: https://chatglm.cn/main/alltoolsdetail?lang=zh
3. 如果出现 **Access Verification**，完成验证

## 步骤2: 打开开发者工具

按 **F12** 或 **Ctrl+Shift+I** 打开开发者工具

## 步骤3: 获取 Cookies

### 方法A: 使用控制台（推荐）

1. 切换到 **控制台(Console)** 标签
2. 粘贴以下代码并回车：

```javascript
// 获取所有 cookies 并格式化为 JSON
const cookies = document.cookie.split(';').map(cookie => {
    const [name, ...valueParts] = cookie.trim().split('=');
    const value = valueParts.join('=');
    return {
        name: name,
        value: value,
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

3. 复制输出的 JSON

### 方法B: 使用应用程序标签

1. 切换到 **应用程序(Application)** 标签
2. 左侧选择 **Cookies** → **https://chatglm.cn**
3. 右键任意 cookie → **复制所有 cookies 为 JSON**

### 方法C: 使用网络标签

1. 切换到 **网络(Network)** 标签
2. 刷新页面 (F5)
3. 点击任意请求
4. 右侧选择 **Cookies** 标签
5. 查看请求 cookies

## 步骤4: 保存 Cookies

将获取的 JSON 保存到文件：

**文件路径**: `F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\zhipuqingyan\cookies\chatglm_cookies.json`

**文件内容格式**:
```json
[
  {
    "name": "cookie_name",
    "value": "cookie_value",
    "domain": ".chatglm.cn",
    "path": "/",
    "expires": -1,
    "httpOnly": false,
    "secure": true,
    "sameSite": "Lax"
  }
]
```

## 步骤5: 配置使用 Edge

修改配置文件 `openclaw.json` 或创建 `.env` 文件：

```json
{
  "common": {
    "browser_type": "edge",
    "edge_path": "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"
  }
}
```

或者在 Python 中设置：
```python
import os
os.environ['BROWSER_TYPE'] = 'edge'
os.environ['EDGE_PATH'] = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
```

## 步骤6: 运行程序

```python
from gs2026.analysis.worker.message.zhipuqingyan import analysis_event_driven
analysis_event_driven(['2026-05-20'])
```

## 常见问题

### Q1: Edge 路径不正确
**解决**: 查找 Edge 实际路径
```powershell
# 在 PowerShell 中运行
Get-ChildItem -Path "C:\Program Files*" -Recurse -Filter "msedge.exe" -ErrorAction SilentlyContinue | Select-Object FullName
```

### Q2: Cookies 格式不正确
**解决**: 使用提供的转换脚本
```python
# 运行转换脚本
python cookies_convert.py
```

### Q3: 验证仍然出现
**解决**: 
1. 确保 cookies 未过期
2. 检查 domain 是否为 `.chatglm.cn`
3. 确保 `secure` 和 `sameSite` 设置正确

## 获取 Cookies 的自动化脚本

创建 `get_cookies_from_edge.py`:

```python
"""从 Edge 浏览器获取 Cookies 的自动化脚本"""

import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

cookies_dir = Path(__file__).parent / 'cookies'
cookies_dir.mkdir(exist_ok=True)
cookies_file = cookies_dir / 'chatglm_cookies.json'

# Edge 路径
edge_path = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'

def get_cookies_from_edge():
    """使用 Edge 获取 cookies"""
    print("=" * 60)
    print("使用 Microsoft Edge 获取 Cookies")
    print("=" * 60)
    print()
    print("步骤:")
    print("1. Edge 浏览器将自动打开")
    print("2. 请手动完成验证（如 Access Verification）")
    print("3. 完成后返回此窗口，按 Enter 键")
    print()
    input("按 Enter 键开始...")
    print()
    
    with sync_playwright() as p:
        print("正在启动 Edge...")
        browser = p.chromium.launch(
            headless=False,
            executable_path=edge_path
        )
        
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
        )
        
        page = context.new_page()
        
        print("正在打开智谱清言...")
        page.goto('https://chatglm.cn/main/alltoolsdetail?lang=zh', timeout=60000)
        print("页面已加载")
        print()
        
        print("请手动完成验证（如需要）")
        print("完成后返回此窗口，按 Enter 键保存 cookies")
        print()
        input("按 Enter 键保存 cookies...")
        print()
        
        # 获取 cookies
        cookies = context.cookies()
        
        # 保存到文件
        with open(cookies_file, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        
        print(f"✓ 已保存 {len(cookies)} 个 cookies 到: {cookies_file}")
        print()
        print("Cookies 列表:")
        for cookie in cookies:
            print(f"  - {cookie.get('name')}: {cookie.get('value', '')[:30]}...")
        
        browser.close()
        print()
        print("=" * 60)
        print("完成！现在可以运行主程序了。")
        print("=" * 60)

if __name__ == "__main__":
    get_cookies_from_edge()
```

运行:
```bash
python get_cookies_from_edge.py
```

## 验证 Cookies 是否有效

创建 `verify_cookies.py`:

```python
"""验证 cookies 是否有效"""

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

cookies_file = Path(__file__).parent / 'cookies' / 'chatglm_cookies.json'
edge_path = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'

def verify_cookies():
    if not cookies_file.exists():
        print("✗ Cookies 文件不存在")
        return False
    
    with open(cookies_file, 'r') as f:
        cookies = json.load(f)
    
    print(f"加载了 {len(cookies)} 个 cookies")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            executable_path=edge_path
        )
        
        context = browser.new_context()
        context.add_cookies(cookies)
        
        page = context.new_page()
        page.goto('https://chatglm.cn/main/alltoolsdetail?lang=zh', timeout=30000)
        
        # 检查是否出现验证页面
        content = page.content()
        if 'Access Verification' in content or '验证' in content:
            print("✗ Cookies 无效，仍需要验证")
            return False
        else:
            print("✓ Cookies 有效，无需验证")
            return True
        
        browser.close()

if __name__ == "__main__":
    verify_cookies()
```
