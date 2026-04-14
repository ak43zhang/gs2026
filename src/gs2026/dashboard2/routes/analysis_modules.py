"""
数据分析模块配置
"""

ANALYSIS_MODULES = {
    'deepseek': {
        'name': 'DeepSeek AI分析',
        'icon': '🤖',
        'type': 'analysis',
        'tasks': {
            'event_driven': {
                'name': '领域事件分析',
                'file': 'analysis/worker/message/deepseek/deepseek_analysis_event_driven.py',
                'function': 'analysis_event_driven',
                'params': [
                    {
                        'name': 'date_list',
                        'type': 'date_list',
                        'label': '分析日期列表',
                        'required': True,
                        'description': '选择需要分析的日期，可添加多个'
                    }
                ]
            },
            'news_cls': {
                'name': '财联社数据分析',
                'file': 'analysis/worker/message/deepseek/deepseek_analysis_news_cls.py',
                'function': 'analysis_news_cls',
                'params': [
                    {
                        'name': 'year',
                        'type': 'select',
                        'label': '年份',
                        'required': True,
                        'default': '2026',
                        'options': [
                            {'value': '2016', 'label': '2016年'},
                            {'value': '2017', 'label': '2017年'},
                            {'value': '2018', 'label': '2018年'},
                            {'value': '2019', 'label': '2019年'},
                            {'value': '2020', 'label': '2020年'},
                            {'value': '2021', 'label': '2021年'},
                            {'value': '2022', 'label': '2022年'},
                            {'value': '2023', 'label': '2023年'},
                            {'value': '2024', 'label': '2024年'},
                            {'value': '2025', 'label': '2025年'},
                            {'value': '2026', 'label': '2026年'}
                        ],
                        'description': '选择分析数据的年份'
                    }
                ]
            },
            'news_combine': {
                'name': '综合数据分析',
                'file': 'analysis/worker/message/deepseek/deepseek_analysis_news_combine.py',
                'function': 'analysis_news_combine',
                'params': [
                    {
                        'name': 'year',
                        'type': 'select',
                        'label': '年份',
                        'required': True,
                        'default': '2026',
                        'options': [
                            {'value': '2016', 'label': '2016年'},
                            {'value': '2017', 'label': '2017年'},
                            {'value': '2018', 'label': '2018年'},
                            {'value': '2019', 'label': '2019年'},
                            {'value': '2020', 'label': '2020年'},
                            {'value': '2021', 'label': '2021年'},
                            {'value': '2022', 'label': '2022年'},
                            {'value': '2023', 'label': '2023年'},
                            {'value': '2024', 'label': '2024年'},
                            {'value': '2025', 'label': '2025年'},
                            {'value': '2026', 'label': '2026年'}
                        ],
                        'description': '选择分析数据的年份'
                    }
                ]
            },
            'news_ztb': {
                'name': '涨停板数据分析',
                'file': 'analysis/worker/message/deepseek/deepseek_analysis_news_ztb.py',
                'function': 'analysis_news_ztb',
                'params': [
                    {
                        'name': 'date_list',
                        'type': 'date_list',
                        'label': '分析日期列表',
                        'required': True,
                        'description': '选择需要分析的日期，可添加多个'
                    }
                ]
            },
            'notice': {
                'name': '公告分析',
                'file': 'analysis/worker/message/deepseek/deepseek_analysis_notice.py',
                'function': 'analysis_notice',
                'params': [
                    {
                        'name': 'year',
                        'type': 'select',
                        'label': '年份',
                        'required': True,
                        'default': '2026',
                        'options': [
                            {'value': '2016', 'label': '2016年'},
                            {'value': '2017', 'label': '2017年'},
                            {'value': '2018', 'label': '2018年'},
                            {'value': '2019', 'label': '2019年'},
                            {'value': '2020', 'label': '2020年'},
                            {'value': '2021', 'label': '2021年'},
                            {'value': '2022', 'label': '2022年'},
                            {'value': '2023', 'label': '2023年'},
                            {'value': '2024', 'label': '2024年'},
                            {'value': '2025', 'label': '2025年'},
                            {'value': '2026', 'label': '2026年'}
                        ],
                        'description': '选择分析数据的年份'
                    }
                ]
            }
        }
    }
}
