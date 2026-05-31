"""一键验证代理 - 获取最佳IP并打开浏览器"""
import sys, subprocess, os
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.analysis.worker.message.deepseek.proxy_pool import get_pool

pool = get_pool()
top = pool.get_top(5)

if not top:
    print("代理池为空，先刷新...")
    pool.refresh(verify=True)
    top = pool.get_top(5)

if not top:
    print("无可用代理！")
    sys.exit(1)

print("可用代理：")
for i, p in enumerate(top, 1):
    print(f"  {i}. {p.url}  |  {p.latency_ms:.0f}ms  |  score={p.score:.0f}")

# 选择最快的
best = top[0]
print(f"\n使用最快代理: {best.url} ({best.latency_ms:.0f}ms)")
print(f"正在打开浏览器访问 chat.deepseek.com ...\n")

# 尝试找到 Chrome 或 Edge
chrome_paths = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]
edge_paths = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

browser_path = None
for p in chrome_paths + edge_paths:
    if os.path.exists(p):
        browser_path = p
        break

if browser_path:
    subprocess.Popen([
        browser_path,
        f"--proxy-server={best.url}",
        "--incognito" if "chrome" in browser_path.lower() else "--inprivate",
        "https://chat.deepseek.com/"
    ])
    print(f"已启动: {os.path.basename(browser_path)}")
    print(f"代理: {best.url}")
    print("\n如果页面正常加载 → IP可用 + DeepSeek未封该IP")
    print("如果超时/403 → 该IP被封或不可用")
else:
    print("未找到浏览器，请手动执行：")
    print(f'  chrome.exe --proxy-server="{best.url}" --incognito https://chat.deepseek.com/')
