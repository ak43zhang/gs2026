"""排查问题3和4"""
from sqlalchemy import create_engine
from gs2026.utils import config_util
import pandas as pd

url = config_util.get_config('common.url')
engine = create_engine(url)

with engine.connect() as conn:
    # 检查continuity分布
    df = pd.read_sql("SELECT continuity, COUNT(1) as cnt FROM analysis_ztb_detail_2026 WHERE has_expect=1 GROUP BY continuity ORDER BY continuity DESC", conn)
    print('=== continuity分布 ===')
    print(df.to_string(index=False))

# 检查生成的HTML是否有概念热度
with open(r'G:\report\智能报告\智能日报_2026-06-05.html', 'r', encoding='utf-8') as f:
    content = f.read()

has_concept = '概念热度' in content
print(f'\n概念热度是否存在: {has_concept}')
if has_concept:
    idx = content.find('概念热度')
    print(content[idx:idx+200])
else:
    # 检查sector热度是否存在
    has_sector = '板块热度' in content
    print(f'板块热度是否存在: {has_sector}')
    # 搜索附录位置
    idx = content.find('附录')
    if idx > 0:
        print(f'附录内容: {content[idx:idx+300]}')
