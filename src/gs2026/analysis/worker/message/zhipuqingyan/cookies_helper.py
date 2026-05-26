"""智谱清言 Cookies 导入工具

支持两种方式:
1. 从浏览器导出 - 使用 get_cookies_manual.py 手动获取
2. 从其他来源导入 - 直接编辑 cookies/chatglm_cookies.json

Cookies 文件格式:
[
    {
        "name": "cookie_name",
        "value": "cookie_value",
        "domain": ".chatglm.cn",
        "path": "/",
        "expires": 1234567890,
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

def show_current_cookies():
    """显示当前 cookies"""
    if cookies_file.exists():
        with open(cookies_file, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        print(f"当前有 {len(cookies)} 个 cookies:")
        for cookie in cookies:
            name = cookie.get('name', 'unknown')
            domain = cookie.get('domain', 'unknown')
            value_preview = cookie.get('value', '')[:50] + '...' if len(cookie.get('value', '')) > 50 else cookie.get('value', '')
            print(f"  - {name} ({domain}): {value_preview}")
    else:
        print("当前没有 cookies 文件")

def import_cookies_from_string(json_str: str):
    """从 JSON 字符串导入 cookies"""
    try:
        cookies = json.loads(json_str)
        if not isinstance(cookies, list):
            print("错误: cookies 必须是数组格式")
            return False
        
        # 保存到文件
        cookies_dir.mkdir(exist_ok=True)
        with open(cookies_file, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        
        print(f"✓ 成功导入 {len(cookies)} 个 cookies")
        return True
    except json.JSONDecodeError as e:
        print(f"错误: JSON 格式不正确 - {e}")
        return False
    except Exception as e:
        print(f"错误: {e}")
        return False

def create_sample_cookies():
    """创建示例 cookies 文件"""
    sample = [
        {
            "name": "sample_cookie",
            "value": "sample_value",
            "domain": ".chatglm.cn",
            "path": "/",
            "expires": -1,
            "httpOnly": False,
            "secure": True,
            "sameSite": "Lax"
        }
    ]
    
    cookies_dir.mkdir(exist_ok=True)
    with open(cookies_file, 'w', encoding='utf-8') as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)
    
    print(f"✓ 示例 cookies 文件已创建: {cookies_file}")
    print("请编辑此文件，替换为实际的 cookies")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == 'show':
            show_current_cookies()
        elif sys.argv[1] == 'sample':
            create_sample_cookies()
        else:
            print("用法:")
            print("  python cookies_helper.py show      - 显示当前 cookies")
            print("  python cookies_helper.py sample    - 创建示例 cookies 文件")
    else:
        print("Cookies 导入工具")
        print()
        print("当前状态:")
        show_current_cookies()
        print()
        print("操作:")
        print("  1. 运行 get_cookies_manual.py 手动获取 cookies")
        print(f"  2. 或直接编辑: {cookies_file}")
