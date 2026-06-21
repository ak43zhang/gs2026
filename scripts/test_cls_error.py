"""Reproduce the exact error"""
import pandas as pd
import re
from datetime import datetime
from gs2026.utils import string_util

def process_datetime(row):
    date_match = re.search(r'(\d{4}\.\d{2}\.\d{2})', row)
    if date_match:
        formatted_date = date_match.group(1).replace('.', '-')
    else:
        formatted_date = datetime.now().strftime('%Y-%m-%d')
    if formatted_date != datetime.now().strftime('%Y-%m-%d'):
        formatted_date = datetime.now().strftime('%Y-%m-%d')
    time_match = re.search(r'(\d{2}:\d{2}:\d{2})', row)
    formatted_time = time_match.group(1) if time_match else '00:00:00'
    return f"{formatted_date} {formatted_time}"

def extract_text(row):
    match = re.search(r'【(.*?)】', row['内容'])
    if match:
        return match.group(1)
    else:
        return row['内容'][:10] if len(row['内容']) >= 10 else row['内容']

# Test with content that has multiple 【】 brackets
test_data = [
    '15:30:00【标题一】内容一',
    '15:31:00【标题二】【标题三】内容二',  # Multiple brackets
    '15:32:00普通内容没有方括号的长文本信息',
]
df = pd.DataFrame(test_data, columns=['内容'])
df['发布时间'] = df['内容'].apply(process_datetime)

print('Test 1 - normal data:')
try:
    df['标题'] = df.apply(extract_text, axis=1)
    print('  OK')
    print(df[['标题']])
except Exception as e:
    print(f'  ERROR: {e}')

# Test with empty content_lists (what happens when selector returns nothing)
print('\nTest 2 - empty list:')
content_lists = []
df2 = pd.DataFrame(content_lists, columns=["内容"])
print(f'  Shape: {df2.shape}')
try:
    df2['发布时间'] = df2['内容'].apply(process_datetime)
    df2['标题'] = df2.apply(extract_text, axis=1)
    print('  OK')
except Exception as e:
    print(f'  ERROR: {e}')

# Test what actually happens with the real page content
import requests
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.cls.cn/telegraph',
}
response = requests.get('https://www.cls.cn/telegraph', headers=headers, timeout=10)
soup = BeautifulSoup(response.text, 'html.parser')
selector = '#__next > div > div.m-auto.w-1200 > div.clearfix.w-100p.p-t-20.p-b-30 > div.f-l.w-894 > div:nth-child(2) > div > div > div.clearfix.m-b-15.f-s-16.telegraph-content-box'
all_contents = soup.select(selector)
print(f'\nTest 3 - real page selector: {len(all_contents)} elements')

content_lists = [content.text for content in all_contents if "【" in content.text]
print(f'  Content lists: {len(content_lists)} items')

if content_lists:
    df3 = pd.DataFrame(content_lists, columns=["内容"])
    df3['发布时间'] = df3['内容'].apply(process_datetime)
    try:
        df3['标题'] = df3.apply(extract_text, axis=1)
        print('  OK')
    except Exception as e:
        print(f'  ERROR: {e}')
        print(f'  df3 shape: {df3.shape}')
        print(f'  df3 columns: {df3.columns.tolist()}')
        # Try to see what apply returns
        result = df3.apply(extract_text, axis=1)
        print(f'  apply result type: {type(result)}')
        print(f'  apply result shape: {result.shape}')
else:
    print('  No content found - page is JS-rendered')
