#!/usr/bin/env python3
"""
大盘日内走势形态识别器

识别大盘日内 7 种走势形态（盘后模式）+ 实时阶段判断（盘中模式）。
数据基础：mkt_vs_open_pct（大盘相对开盘涨跌幅）构建的日内净值曲线。

使用方式：
    # 盘后：识别整天走势形态
    python scripts/detect_market_shape.py 20260713 --mode eod

    # 盘中：判断指定时刻所处的阶段（回溯测试）
    python scripts/detect_market_shape.py 20260713 --mode realtime --time 13:30

    # 直接修改下方 CONFIG 运行
    python scripts/detect_market_shape.py

7 种形态（盘后）：
    横盘震荡 / 单边上行 / 单边下行 / 低开高走(反转向上)
    / 高开低走(反转向下) / V型反转 / 倒V(冲高回落)

盘中阶段：
    下行中 / 下行后反弹初期 / 反转向上确认
    / 上行中 / 上行后回落初期 / 反转向下确认 / 横盘
"""

# ==================== 参数配置区 ====================
CONFIG = {
    'date': '20260713',
    'mode': 'eod',              # 'eod'(盘后形态) | 'realtime'(盘中阶段)
    'realtime_time': '13:30',   # realtime模式的截止时刻 HH:MM

    # 形态判定阈值（自适应：基于当天振幅比例）
    'flat_range': 0.5,          # 全天振幅<0.5%判横盘（对应弱市下限）
    'significant_ratio': 0.5,   # "显著"转折 = 全天振幅 × 0.5
    'breakout_ratio': 0.3,      # "真高开/真低开" = 全天振幅 × 0.3
    'edge_ratio': 0.2,          # 极值"接近开盘"容差 = 全天振幅 × 0.2

    # 盘中实时参数
    'rt_confirm_minutes': 10,   # 反转确认所需持续分钟
    'rt_just_extreme_min': 3,   # 极值"刚创出"的分钟界限
}
# ================================================================

import sys
import argparse
import json

import numpy as np
import pandas as pd
from sqlalchemy import text

from gs2026.utils import config_util


def get_engine():
    return config_util.get_engine()


def load_mkt_curve(date_str: str) -> pd.DataFrame:
    """
    加载大盘日内净值曲线（mkt_vs_open_pct）

    大盘指标存储在 ext_indicators JSON 中，同一时刻所有债券相同。
    只取一只全天成交的债券即可（避免全表GROUP BY）。

    Returns:
        DataFrame(time, vs_open)  空表返回空DataFrame
    """
    engine = get_engine()
    table = f"monitor_zq_sssj_{date_str}"
    with engine.connect() as conn:
        code_df = pd.read_sql(text(f"""
            SELECT bond_code FROM {table}
            WHERE time >= '14:50:00' LIMIT 1
        """), conn)
        if code_df.empty:
            return pd.DataFrame()
        code = code_df['bond_code'].iloc[0]
        df = pd.read_sql(text(f"""
            SELECT time, ext_indicators FROM {table}
            WHERE bond_code = :c AND time >= '09:30:00'
              AND ext_indicators IS NOT NULL
            ORDER BY time
        """), conn, params={'c': code})

    if df.empty:
        return pd.DataFrame()

    def _get_vs(js):
        try:
            d = json.loads(js) if isinstance(js, str) else {}
            v = d.get('mkt_vs_open_pct')
            return float(v) if v is not None else None
        except Exception:
            return None

    df['vs_open'] = df['ext_indicators'].apply(_get_vs)
    df = df.dropna(subset=['vs_open']).reset_index(drop=True)
    return df[['time', 'vs_open']]


def calc_structure(df: pd.DataFrame) -> dict:
    """计算日内净值曲线的结构指标"""
    vs = df['vs_open'].values
    n = len(vs)
    high_idx = int(np.argmax(vs))
    low_idx = int(np.argmin(vs))
    return {
        'n': n,
        'open_pct': float(vs[0]),
        'close_pct': float(vs[-1]),
        'high_pct': float(vs.max()),
        'low_pct': float(vs.min()),
        'high_idx': high_idx,
        'low_idx': low_idx,
        'high_pos': high_idx / n,
        'low_pos': low_idx / n,
        'high_time': df['time'].iloc[high_idx],
        'low_time': df['time'].iloc[low_idx],
        'total_range': float(vs.max() - vs.min()),
        'recovery_from_low': float(vs[-1] - vs.min()),
        'drawdown_from_high': float(vs.max() - vs[-1]),
        'down_leg': float(vs[0] - vs.min()),   # 开盘到最低
        'up_leg': float(vs.max() - vs[0]),     # 开盘到最高
    }


def classify_shape_eod(st: dict) -> tuple:
    """
    盘后形态分类（7种）

    优先级：横盘 → 单边下行 → 单边上行 → V型 → 倒V → 低开高走 → 高开低走 → 混合
    Returns: (形态名, 理由)
    """
    R = st['total_range']
    significant = R * CONFIG['significant_ratio']
    real_breakout = R * CONFIG['breakout_ratio']

    high_pct, low_pct, close_pct = st['high_pct'], st['low_pct'], st['close_pct']
    high_pos, low_pos = st['high_pos'], st['low_pos']
    recovery, drawdown = st['recovery_from_low'], st['drawdown_from_high']
    down_leg, up_leg = st['down_leg'], st['up_leg']

    if R < CONFIG['flat_range']:
        return "横盘震荡", f"全天振幅{R:.2f}%<{CONFIG['flat_range']}%，波动过小"

    # 单边下行：高点≈开盘(未真冲高) + 收盘≈日低 + 低点靠后
    if high_pct < real_breakout and (close_pct - low_pct) < significant and low_pos > 0.5:
        return "单边下行", (f"高点{high_pct:+.2f}%≈开盘(未冲高)，"
                          f"收盘{close_pct:+.2f}%接近日低{low_pct:.2f}%，低点在尾段(pos={low_pos:.0%})")

    # 单边上行：低点≈开盘(未真下探) + 收盘≈日高 + 高点靠后
    if abs(low_pct) < real_breakout and (high_pct - close_pct) < significant and high_pos > 0.5:
        return "单边上行", (f"低点{low_pct:+.2f}%≈开盘(未下探)，"
                          f"收盘{close_pct:+.2f}%接近日高{high_pct:.2f}%，高点在尾段(pos={high_pos:.0%})")

    # V型反转：最低点在中段 + 两侧都显著
    if 0.25 < low_pos < 0.75 and down_leg > significant and recovery > significant:
        return "V型反转", f"最低点在中段(pos={low_pos:.0%})，下跌{down_leg:.2f}%后回升{recovery:.2f}%"

    # 倒V(冲高回落)：最高点在中段 + 两侧都显著
    if 0.25 < high_pos < 0.75 and up_leg > significant and drawdown > significant:
        return "倒V(冲高回落)", f"最高点在中段(pos={high_pos:.0%})，上涨{up_leg:.2f}%后回落{drawdown:.2f}%"

    # 低开高走：低点在前半段 + 之后显著回升
    if low_pos < 0.5 and recovery > significant:
        return "低开高走(反转向上)", f"最低点在前半段(pos={low_pos:.0%})，之后回升{recovery:.2f}%"

    # 高开低走：真高开(冲到显著正值) + 高点在前半段 + 之后显著回落
    if high_pct > real_breakout and high_pos < 0.5 and drawdown > significant:
        return "高开低走(反转向下)", f"最高点{high_pct:+.2f}%(真高开,pos={high_pos:.0%})，之后回落{drawdown:.2f}%"

    return "混合/震荡", (f"无明确形态(高{high_pct:+.2f}%@{high_pos:.0%} "
                        f"低{low_pct:+.2f}%@{low_pos:.0%} 收{close_pct:+.2f}%)")


def _time_to_minutes(t: str) -> float:
    """HH:MM:SS 或 HH:MM → 分钟数"""
    parts = str(t).split(':')
    h, m = int(parts[0]), int(parts[1])
    s = int(parts[2]) if len(parts) > 2 else 0
    return h * 60 + m + s / 60


def classify_stage_realtime(df: pd.DataFrame, cutoff_time: str) -> dict:
    """
    盘中实时阶段判断（基于开盘到cutoff_time的数据）

    Returns: dict(stage, detail, ...)
    """
    # 截取到cutoff时刻
    cutoff_min = _time_to_minutes(cutoff_time + ':00' if cutoff_time.count(':') == 1 else cutoff_time)
    df = df[df['time'].apply(_time_to_minutes) <= cutoff_min].reset_index(drop=True)
    if df.empty:
        return {'stage': '无数据', 'detail': f'{cutoff_time}前无数据'}

    st = calc_structure(df)
    R = st['total_range']
    significant = R * CONFIG['significant_ratio']

    cur = st['close_pct']  # 当前值(截止时刻)
    low_pct, high_pct = st['low_pct'], st['high_pct']
    recovery = cur - low_pct
    drawdown = high_pct - cur

    # 距极值的分钟数
    cur_min = _time_to_minutes(df['time'].iloc[-1])
    mins_since_low = cur_min - _time_to_minutes(st['low_time'])
    mins_since_high = cur_min - _time_to_minutes(st['high_time'])

    confirm = CONFIG['rt_confirm_minutes']
    just = CONFIG['rt_just_extreme_min']

    # 阶段判定
    if R < CONFIG['flat_range']:
        stage = "横盘"
        detail = f"振幅{R:.2f}%过小，无明确方向"
    elif mins_since_low < just:
        stage = "下行中"
        detail = f"刚创日内新低{low_pct:.2f}%({int(mins_since_low)}分钟内)"
    elif mins_since_high < just:
        stage = "上行中"
        detail = f"刚创日内新高{high_pct:+.2f}%({int(mins_since_high)}分钟内)"
    elif recovery > significant and mins_since_low > confirm:
        stage = "反转向上确认"
        detail = f"脱离最低点{int(mins_since_low)}分钟，回升{recovery:.2f}%(>{significant:.2f}%)"
    elif drawdown > significant and mins_since_high > confirm:
        stage = "反转向下确认"
        detail = f"脱离最高点{int(mins_since_high)}分钟，回落{drawdown:.2f}%(>{significant:.2f}%)"
    elif recovery > 0 and mins_since_low >= just:
        stage = "下行后反弹初期"
        detail = f"脱离最低点{int(mins_since_low)}分钟，回升{recovery:.2f}%(未达确认阈值{significant:.2f}%)"
    elif drawdown > 0 and mins_since_high >= just:
        stage = "上行后回落初期"
        detail = f"脱离最高点{int(mins_since_high)}分钟，回落{drawdown:.2f}%(未达确认阈值{significant:.2f}%)"
    else:
        stage = "横盘"
        detail = "无明确方向"

    return {
        'stage': stage, 'detail': detail,
        'cur': cur, 'high': high_pct, 'low': low_pct,
        'high_time': st['high_time'], 'low_time': st['low_time'],
        'mins_since_low': mins_since_low, 'mins_since_high': mins_since_high,
        'recovery': recovery, 'drawdown': drawdown,
    }


def main():
    parser = argparse.ArgumentParser(description='大盘日内走势形态识别器')
    parser.add_argument('date', nargs='?', help='日期 YYYYMMDD')
    parser.add_argument('--mode', choices=['eod', 'realtime'], help='eod盘后 | realtime盘中')
    parser.add_argument('--time', help='realtime模式的截止时刻 HH:MM')
    args = parser.parse_args()

    date_str = args.date or CONFIG['date']
    mode = args.mode or CONFIG['mode']
    rt_time = args.time or CONFIG['realtime_time']

    df = load_mkt_curve(date_str)
    if df.empty:
        print(f"日期 {date_str} 无数据")
        return

    if mode == 'eod':
        st = calc_structure(df)
        shape, reason = classify_shape_eod(st)
        print(f"日期 {date_str} 走势形态分析（盘后）")
        print("=" * 60)
        print(f"净值: 开盘0% → 最高{st['high_pct']:+.2f}%({st['high_time']}) "
              f"→ 最低{st['low_pct']:+.2f}%({st['low_time']}) → 收盘{st['close_pct']:+.2f}%")
        print(f"日内振幅: {st['total_range']:.2f}% | 高点位置{st['high_pos']:.0%} 低点位置{st['low_pos']:.0%}")
        print(f"从低点回升{st['recovery_from_low']:.2f}% | 从高点回落{st['drawdown_from_high']:.2f}%")
        print()
        print(f"【形态判定】{shape}")
        print(f"  理由: {reason}")
    else:  # realtime
        r = classify_stage_realtime(df, rt_time)
        print(f"日期 {date_str} 截至 {rt_time} 的实时阶段判断（盘中）")
        print("=" * 60)
        if r['stage'] == '无数据':
            print(r['detail'])
            return
        print(f"到目前: 最高{r['high']:+.2f}%({r['high_time']}) "
              f"最低{r['low']:+.2f}%({r['low_time']}) 当前{r['cur']:+.2f}%")
        print(f"距最低点: {int(r['mins_since_low'])}分钟 | 从最低点回升: {r['recovery']:+.2f}%")
        print(f"距最高点: {int(r['mins_since_high'])}分钟 | 从最高点回落: {r['drawdown']:+.2f}%")
        print()
        print(f"【当前阶段】{r['stage']}")
        print(f"  说明: {r['detail']}")
        print(f"  ⚠️ 盘中判断仅供参考，无法预测后续走势")


if __name__ == '__main__':
    main()
