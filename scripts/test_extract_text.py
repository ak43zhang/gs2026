"""Test extract_text function"""
import pandas as pd
import re
from datetime import datetime

def extract_text(row):
    match = re.search(r'【(.*?)】', row['内容'])
    if match:
        return match.group(1)
    else:
        return row['内容'][:10] if len(row['内容']) >= 10 else row['内容']

def process_datetime(row):
    time_match = re.search(r'(\d{2}:\d{2}:\d{2})', row)
    formatted_time = time_match.group(1) if time_match else '00:00:00'
    return f"{datetime.now().strftime('%Y-%m-%d')} {formatted_time}"

# Test with sample data
test_data = ['15:30:00【测试标题】这是一条测试内容', '15:31:00没有方括号的内容信息比较长']
df = pd.DataFrame(test_data, columns=['内容'])
df['发布时间'] = df['内容'].apply(process_datetime)

print('Before extract_text:')
print(df)
print(f'df columns: {df.columns.tolist()}')

result = df.apply(extract_text, axis=1)
print(f'\nresult type: {type(result)}')
print(f'result:\n{result}')

df['标题'] = result
print('\nAfter:')
print(df)
print('\nSuccess - no error')
