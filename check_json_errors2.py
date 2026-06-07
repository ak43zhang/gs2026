"""深入分析JSON错误的具体字符"""
from sqlalchemy import create_engine, text
from gs2026.utils import config_util
import pandas as pd
import re

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    samples = pd.read_sql(
        'SELECT id, module_name, raw_json, error_msg FROM analysis_json_errors ORDER BY id DESC LIMIT 5',
        conn
    )

for _, row in samples.iterrows():
    err = row['error_msg']
    raw = row['raw_json'] or ''
    m = re.search(r'char (\d+)', err)
    if not m:
        continue
    pos = int(m.group(1))

    print(f"\n{'='*60}")
    print(f"id={row['id']} [{row['module_name']}] 总长={len(raw)} 错误位置=char {pos}")
    print(f"错误信息: {err}")

    # 显示错误位置前后的字符（含repr以看清不可见字符）
    start = max(0, pos - 30)
    end = min(len(raw), pos + 30)
    snippet = raw[start:end]
    print(f"\n原文片段(repr):")
    print(repr(snippet))

    # 具体错误字符
    if pos < len(raw):
        print(f"\n错误位置字符: {repr(raw[pos])}")
        print(f"前5字符: {repr(raw[max(0,pos-5):pos])}")
        print(f"后5字符: {repr(raw[pos:pos+5])}")
    else:
        print(f"\n错误位置超出JSON长度（截断？）")

    # 检查该行内容
    lines = raw.split('\n')
    line_match = re.search(r'line (\d+)', err)
    if line_match:
        line_num = int(line_match.group(1))
        if line_num <= len(lines):
            line_content = lines[line_num - 1]
            print(f"\n第{line_num}行内容:")
            print(repr(line_content[:200]))
