"""验证json-repair对错误数据的修复效果"""
from sqlalchemy import create_engine
from gs2026.utils import config_util
from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_client import repair_llm_json
import pandas as pd
import json

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    samples = pd.read_sql('SELECT id, module_name, raw_json FROM analysis_json_errors ORDER BY id DESC LIMIT 10', conn)

success = 0
fail = 0
for _, row in samples.iterrows():
    raw = row['raw_json']
    rid = row['id']
    module = row['module_name']
    try:
        repaired = repair_llm_json(raw)
        obj = json.loads(repaired)
        success += 1
        keys = list(obj.keys())[:3]
        print(f"id={rid} [{module}]: OK (keys={keys})")
    except Exception as e:
        fail += 1
        print(f"id={rid} [{module}]: FAIL - {e}")

print(f"\n结果: {success}/{success+fail} 修复成功")
