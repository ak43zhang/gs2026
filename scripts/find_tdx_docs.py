#!/usr/bin/env python3
"""
查找docs目录中包含tdx或实时数据的文档
"""

from pathlib import Path

DOCS_DIR = Path("F:/pyworkspace2026/gs2026/docs")

keywords = ['tdx', '实时', '3秒', 'tick', 'pytdx', 'get_bond_tdx']

def find_docs():
    found = []
    for md_file in DOCS_DIR.rglob("*.md"):
        try:
            with open(md_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                for kw in keywords:
                    if kw in content.lower() or kw in md_file.name.lower():
                        found.append(str(md_file.relative_to(DOCS_DIR)))
                        break
        except:
            pass
    return found

if __name__ == '__main__':
    docs = find_docs()
    print("找到相关文档：")
    for d in docs:
        print(f"  {d}")
