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
                'params': []
            },
            'news_combine': {
                'name': '综合数据分析',
                'file': 'analysis/worker/message/deepseek/deepseek_analysis_news_combine.py',
                'function': 'analysis_news_combine',
                'params': []
            },
            'news_ztb': {
                'name': '涨停板数据分析',
                'file': 'analysis/worker/message/deepseek/deepseek_analysis_news_ztb.py',
                'function': 'analysis_news_ztb',
                'params': []
            },
            'notice': {
                'name': '公告分析',
                'file': 'analysis/worker/message/deepseek/deepseek_analysis_notice.py',
                'function': 'analysis_notice',
                'params': []
            }
        }
    }
}
