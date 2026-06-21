"""验证去重逻辑"""
import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.collection.news.cls_history import get_cls

df = get_cls('https://www.cls.cn/telegraph')
print(f'Columns: {df.columns.tolist()}')
print(f'\n内容hash 示例:')
print(df[['标题', '发布时间', '内容hash']].head(3).to_string())

unique_count = df['内容hash'].nunique()
total_count = len(df)
print(f'\n去重字段: 内容hash (标题+发布时间 的 MD5)')
print(f'唯一hash数: {unique_count} / 总行数: {total_count}')
print(f'是否有重复: {"是" if unique_count < total_count else "否"}')
