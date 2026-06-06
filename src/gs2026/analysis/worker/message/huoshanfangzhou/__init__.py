"""火山方舟分析模块初始化"""

from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_client import (
    VolcengineClient,
    volcengine_analysis,
    VOLCENGINE_MODEL,
)

from gs2026.analysis.worker.message.huoshanfangzhou.analysis_event_driven import (
    volcengine_ai,
    area_ai_analysis,
    area_ai,
    analysis_event_driven,
)

from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_analysis_news_cls import (
    volcengine_ai as volcengine_ai_news,
    get_news_cls_analysis,
    time_task_do_cls,
)

from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_analysis_news_combine import (
    volcengine_ai as volcengine_ai_combine,
    get_news_combine_analysis,
    time_task_do_combine,
)

from gs2026.analysis.worker.message.huoshanfangzhou.volcengine_analysis_news_ztb import (
    volcengine_ai as volcengine_ai_ztb,
    get_news_ztb_analysis,
    time_task_do_ztb,
    analysis_ztb,
)

__all__ = [
    'VolcengineClient',
    'volcengine_analysis',
    'VOLCENGINE_MODEL',
    'volcengine_ai',
    'area_ai_analysis',
    'area_ai',
    'analysis_event_driven',
    'volcengine_ai_news',
    'get_news_cls_analysis',
    'time_task_do_cls',
    'volcengine_ai_combine',
    'get_news_combine_analysis',
    'time_task_do_combine',
    'volcengine_ai_ztb',
    'get_news_ztb_analysis',
    'time_task_do_ztb',
    'analysis_ztb',
]
