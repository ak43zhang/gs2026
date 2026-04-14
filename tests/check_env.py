"""
对比测试：PyCharm vs 命令行环境差异
"""
import sys
import os

print("=" * 60)
print("环境信息对比")
print("=" * 60)

print(f"\n[Python]")
print(f"  Executable: {sys.executable}")
print(f"  Version: {sys.version}")

print(f"\n[工作目录]")
print(f"  CWD: {os.getcwd()}")

print(f"\n[sys.path]")
for i, p in enumerate(sys.path):
    print(f"  [{i}] {p}")

print(f"\n[环境变量]")
print(f"  PYTHONPATH: {os.environ.get('PYTHONPATH', 'Not set')}")
print(f"  PATH (前200字符): {os.environ.get('PATH', '')[:200]}...")

print(f"\n[Playwright 浏览器]")
from pathlib import Path
user = os.environ.get('USERNAME', os.environ.get('USER', 'unknown'))
firefox_path = f"C:/Users/{user}/AppData/Local/ms-playwright/firefox-1509/firefox/firefox.exe"
print(f"  Firefox 路径: {firefox_path}")
print(f"  Firefox 存在: {Path(firefox_path).exists()}")

print("\n" + "=" * 60)
