#!/usr/bin/env python
# -*- coding: utf-8 -*-

# 模拟判断逻辑
script_name = 'news/cls_history.py'

news_scripts = ['collection_message.py', 'cls_history.py', 'dicj_yckx.py', 
               'hot_api.py', 'xhcj.py', 'zqsb_rmcx.py']

is_news = script_name in news_scripts or any(script_name.endswith(f'news/{s}') for s in news_scripts)

print(f"script_name: {script_name}")
print(f"is_news: {is_news}")
print(f"script_name in news_scripts: {script_name in news_scripts}")
print(f"any endswith: {any(script_name.endswith(f'news/{s}') for s in news_scripts)}")

# 正确的判断应该是
pure_name = script_name.split('/')[-1] if '/' in script_name else script_name
is_news_correct = pure_name in news_scripts
print(f"\npure_name: {pure_name}")
print(f"is_news_correct: {is_news_correct}")
