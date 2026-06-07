"""分析 analysis_json_errors 表中的错误样本"""
from sqlalchemy import create_engine, text
from gs2026.utils import config_util
import pandas as pd

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    df = pd.read_sql('SELECT id, module_name, error_msg, json_length, create_time FROM analysis_json_errors ORDER BY create_time DESC LIMIT 20', conn)

print(f'总记录数: {len(df)}')
print()
print('=== 按模块统计 ===')
print(df['module_name'].value_counts().to_string())
print()
print('=== 错误详情 ===')
for _, row in df.iterrows():
    print(f"[id={row['id']}] [{row['module_name']}] len={row['json_length']} | {row['error_msg'][:100]}")

# 抽样查看具体JSON内容（取前3条，看错误位置附近）
print('\n=== 抽样JSON内容（错误位置附近）===')
with engine.connect() as conn:
    samples = pd.read_sql('SELECT id, module_name, raw_json, error_msg FROM analysis_json_errors ORDER BY create_time DESC LIMIT 3', conn)

for _, row in samples.iterrows():
    err = row['error_msg']
    raw = row['raw_json'] or ''
    # 提取char位置
    import re
    m = re.search(r'char (\d+)', err)
    if m:
        pos = int(m.group(1))
        start = max(0, pos - 50)
        end = min(len(raw), pos + 50)
        snippet = raw[start:end]
        print(f"\n--- id={row['id']} [{row['module_name']}] char={pos} ---")
        print(f"...{snippet}...")
        print(f"     {'':>{pos-start}}^ 错误位置")
    else:
        print(f"\n--- id={row['id']} [{row['module_name']}] ---")
        print(f"错误: {err}")
        print(f"末尾50字符: ...{raw[-50:]}")
