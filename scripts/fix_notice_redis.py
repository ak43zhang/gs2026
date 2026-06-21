"""Fix notice.py Redis lock"""
with open(r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\deepseek\deepseek_analysis_notice.py', encoding='utf-8') as f:
    content = f.read()

old_text = '''            if 0 < len(lists) < 30:
                # 数据量较少时全量分析
                deepseek_ai(lists, notice_type_dic_str, table_name, analysis_table_name, _headless)
            if len(lists) >= 30:
                # 数据量较大时随机采样15-18条，控制单次Prompt长度
                sample_list: List[List[Any]] = random.sample(lists, 30)
                deepseek_ai(sample_list, notice_type_dic_str, table_name, analysis_table_name, _headless)
            else:
                # 无待分析数据，返回False终止轮询
                flag = False'''

new_text = '''            if len(lists) > 0:
                # 过滤已被其他进程锁定的消息
                available = [item for item in lists if not redis_client.exists(f"news_ai_lock:{table_name}:{item[0]}")]
                if not available:
                    logger.info("所有消息已被锁定，暂不处理")
                    time.sleep(60)
                else:
                    # 采样
                    sample_list = random.sample(available, min(30, len(available))) if len(available) >= 30 else available
                    # 加锁（15分钟）
                    for item in sample_list:
                        redis_client.set(f"news_ai_lock:{table_name}:{item[0]}", '1', ex=900)
                    deepseek_ai(sample_list, notice_type_dic_str, table_name, analysis_table_name, _headless)
            else:
                # 无待分析数据，返回False终止轮询
                flag = False'''

if old_text in content:
    content = content.replace(old_text, new_text)
    with open(r'F:\pyworkspace2026\gs2026\src\gs2026\analysis\worker\message\deepseek\deepseek_analysis_notice.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('OK')
else:
    print('Not found')
