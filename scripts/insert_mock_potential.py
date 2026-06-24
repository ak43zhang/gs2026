"""
插入模拟潜在标的数据（用于测试前端展示）
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import json
from datetime import datetime
from sqlalchemy import create_engine, text
from gs2026.utils import config_util

def get_engine():
    url = config_util.get_config('common.url')
    return create_engine(url)

def insert_mock_data():
    engine = get_engine()
    trading_date = '2026-06-24'
    trigger_time = datetime.now().strftime('%H:%M:%S')
    
    # 模拟数据
    mock_data = [
        {
            'code': '000001',
            'name': '平安银行',
            'rank': 1,
            'mainline_count': 3,
            'mainlines': [
                {'name': '银行', 'reason': '银行股龙头，受益于利率上行', 'evidence': '近期资金持续流入'},
                {'name': '大金融', 'reason': '金融板块核心标的', 'evidence': '板块轮动效应'},
                {'name': '高股息', 'reason': '股息率超过5%', 'evidence': '年报披露分红方案'}
            ],
            'score': 92,
            'entry': '开盘竞价介入，或回踩5日线低吸',
            'risk': '低',
            'logic': '银行主线龙头已涨停，该股为板块中军，存在补涨逻辑，且高股息属性受机构青睐'
        },
        {
            'code': '300001',
            'name': '特锐德',
            'rank': 2,
            'mainline_count': 2,
            'mainlines': [
                {'name': '充电桩', 'reason': '充电桩运营龙头', 'evidence': '市占率第一'},
                {'name': '新能源', 'reason': '受益新能源汽车渗透率提升', 'evidence': '政策利好'}
            ],
            'score': 88,
            'entry': '放量突破前高时介入',
            'risk': '中',
            'logic': '充电桩政策利好频出，龙头特来电已独立上市预期，存在估值重塑空间'
        },
        {
            'code': '600519',
            'name': '贵州茅台',
            'rank': 3,
            'mainline_count': 2,
            'mainlines': [
                {'name': '白酒', 'reason': '白酒绝对龙头', 'evidence': '品牌护城河深厚'},
                {'name': '消费复苏', 'reason': '受益于消费场景恢复', 'evidence': '端午动销良好'}
            ],
            'score': 85,
            'entry': '回调至年线附近布局',
            'risk': '低',
            'logic': '白酒板块估值修复，茅台作为风向标，机构配置需求强劲'
        }
    ]
    
    sql = """
        INSERT INTO stock_anomaly_potential
        (trading_date, trigger_time, trigger_type, stock_code, stock_name,
         rank_num, mainline_count, mainlines, total_score, suggested_entry,
         risk_level, logic)
        VALUES
        (:date, :time, :type, :code, :name, :rank, :ml_count, :mls, :score,
         :entry, :risk, :logic)
        ON DUPLICATE KEY UPDATE
        stock_name = VALUES(stock_name),
        mainline_count = VALUES(mainline_count),
        mainlines = VALUES(mainlines),
        total_score = VALUES(total_score),
        suggested_entry = VALUES(suggested_entry),
        risk_level = VALUES(risk_level),
        logic = VALUES(logic)
    """
    
    with engine.connect() as conn:
        for item in mock_data:
            conn.execute(text(sql), {
                'date': trading_date,
                'time': trigger_time,
                'type': 'manual',
                'code': item['code'],
                'name': item['name'],
                'rank': item['rank'],
                'ml_count': item['mainline_count'],
                'mls': json.dumps(item['mainlines'], ensure_ascii=False),
                'score': item['score'],
                'entry': item['entry'],
                'risk': item['risk'],
                'logic': item['logic']
            })
        conn.commit()
    
    print(f"[OK] 插入 {len(mock_data)} 条模拟数据")
    print(f"    日期: {trading_date}")
    print(f"    时间: {trigger_time}")

if __name__ == '__main__':
    insert_mock_data()
