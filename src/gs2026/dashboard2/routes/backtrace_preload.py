#!/usr/bin/env python3
"""
股债交集回溯 - 数据预加载模块（性能优化）

核心思想：把逐tick查库（~2.6万次）改为一次性全量加载（5次），
在内存中构建时间线，遍历时按时间点切片，字段计算规则与enrich完全一致。

字段来源（已代码实测确认）：
- count: top30表累计上榜行数（COUNT WHERE time<=t）
- window_count: top30表window_count列，取当前10分钟窗口内最新记录值，无则0
- change_pct/main_net_amount: 股票sssj表（time=t那一刻）
- change_pct/amount/price: 债券sssj表（time=t那一刻）
- bond_code/industry_name: 股债映射缓存（get_cache）
- is_green/is_green_bond: 绿名单集合
"""
import logging
import pandas as pd

logger = logging.getLogger(__name__)


def _window_start(time_str: str) -> str:
    """当前10分钟窗口起点：HH:(mm//10*10):00"""
    hh = time_str[:2]
    mm = int(time_str[3:5])
    return f"{hh}:{(mm // 10) * 10:02d}:00"


def preload_top30(engine, date: str, asset_type: str, start_time: str = None, end_time: str = None):
    """一次性加载top30全量，构建 count时间线 + window_count时间线所需的原始行

    Args:
        start_time/end_time: 可选，限定加载的时间范围（缩小数据量）
        注意：count是累计值，需从开盘起算，所以count用的数据不能按start_time截断；
        但window_count只看当前窗口，可按窗口起点截断。
        为保证count正确，top30始终从开盘加载到end_time。

    Returns:
        rows: [(code, name, time, window_count), ...] 按time升序
    """
    prefix = 'gp' if asset_type == 'stock' else 'zq'
    table = f"monitor_{prefix}_top30_{date}"
    from sqlalchemy import text
    # count需累计，从开盘起算；只用end_time上界裁剪（减少数据量）
    where = ""
    params = {}
    if end_time:
        where = "WHERE time <= :et"
        params['et'] = end_time
    sql = text(f"SELECT code, name, time, window_count FROM {table} {where} ORDER BY time")
    with engine.connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    result = []
    for r in rows:
        result.append((
            str(r[0]).zfill(6),
            r[1],
            r[2],
            int(r[3]) if r[3] is not None else 0,
        ))
    logger.info(f"[预加载] {table}: {len(result)} 行 (end<={end_time})")
    return result


def preload_sssj(engine, date: str, asset_type: str, start_time: str = None,
                 end_time: str = None, codes: list = None):
    """一次性加载sssj，按time分组成切片字典

    Args:
        start_time/end_time: 时间范围裁剪
        codes: 可选，只加载这些code（WHERE code IN），大幅减少全市场无关行

    Returns:
        {time_str: {code: {字段...}}}
    """
    from sqlalchemy import text
    if asset_type == 'stock':
        table = f"monitor_gp_sssj_{date}"
        code_col = 'stock_code'
        field_cols = ['change_pct', 'main_net_amount']
        select_cols = "stock_code, time, change_pct, main_net_amount"
    else:
        table = f"monitor_zq_sssj_{date}"
        code_col = 'bond_code'
        field_cols = ['change_pct', 'amount', 'price']
        select_cols = "bond_code, time, change_pct, amount, price"

    conds = []
    params = {}
    if start_time:
        conds.append("time >= :st")
        params['st'] = start_time
    if end_time:
        conds.append("time <= :et")
        params['et'] = end_time
    # code过滤：只加载top30候选code（去除全市场无关股票）
    if codes:
        # 去零填充差异：sssj的code可能不带前导0，用两种形式都匹配
        code_set = set()
        for c in codes:
            cs = str(c)
            code_set.add(cs)
            code_set.add(cs.zfill(6))
            code_set.add(cs.lstrip('0') or '0')
        code_list = list(code_set)
        # 用参数化IN
        placeholders = ",".join([f":c{i}" for i in range(len(code_list))])
        conds.append(f"{code_col} IN ({placeholders})")
        for i, c in enumerate(code_list):
            params[f'c{i}'] = c

    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    sql = text(f"SELECT {select_cols} FROM {table} {where}")

    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params=params)

    if df.empty:
        logger.info(f"[预加载] {table}: 空 (范围{start_time}~{end_time}, codes={len(codes) if codes else 0})")
        return {}

    df[code_col] = df[code_col].astype(str).str.zfill(6)

    sliced = {}
    for t, g in df.groupby('time'):
        sliced[t] = g.set_index(code_col)[field_cols].to_dict('index')

    logger.info(f"[预加载] {table}: {len(df)} 行, {len(sliced)} 个时间点 (范围{start_time}~{end_time}, codes过滤={bool(codes)})")
    return sliced


def get_candidate_codes(rows):
    """从top30行提取候选code集合（去零填充统一）"""
    return list({r[0] for r in rows})


def build_count_timeline(rows, timestamps):
    """构建count累计时间线（running累加，指针扫描）

    Args:
        rows: preload_top30返回的 [(code,name,time,wc), ...] 按time升序
        timestamps: 目标时间点列表（升序）

    Returns:
        (count_timeline, name_map)
        count_timeline: {time: {code: 累计count}}
        name_map: {code: name}
    """
    count_timeline = {}
    name_map = {}
    counter = {}
    idx = 0
    n = len(rows)
    for t in timestamps:
        while idx < n and rows[idx][2] <= t:
            code = rows[idx][0]
            counter[code] = counter.get(code, 0) + 1
            name_map[code] = rows[idx][1]
            idx += 1
        # 快照（浅拷贝当前累计）
        count_timeline[t] = dict(counter)
    return count_timeline, name_map


def build_window_count_timeline(rows, timestamps):
    """构建window_count时间线（与 _get_*_window_count_batch 逻辑一致）

    规则：某time下，code的window_count = 该code在[window_start, time]内最新记录的window_count列值；
         窗口内无记录则为0。

    实现：对每个time，需要知道每个code在当前窗口内的最新记录。
    高效做法：按窗口分组预处理。遍历rows一次，按 (窗口起点) 归类，
    维护"当前窗口内每个code的最新(time,wc)"。当时间跨到新窗口时重置。

    但timestamps可能跨多个窗口，且同一窗口内多个time点共享同一窗口起点。
    采用：对每个time点，用该窗口内 time<=当前 的最新记录。

    Returns:
        {time: {code: window_count}}
    """
    wc_timeline = {}
    # 按窗口分组rows：{window_start: [(code, time, wc), ...]}（升序）
    # rows已按time升序，遍历时用指针
    # 对每个time点：窗口=window_start(time)，取该窗口内 time<=当前 每个code最新wc
    # 为高效，维护 current_window 和 该窗口内 {code: (latest_time, wc)}
    current_window = None
    window_latest = {}  # {code: wc}（当前窗口内截至扫描位置的最新值）
    idx = 0
    n = len(rows)

    for t in timestamps:
        ws = _window_start(t)
        # 若进入新窗口，重置
        if ws != current_window:
            current_window = ws
            window_latest = {}
            # 指针回退处理：rows按time升序，需把idx定位到 >= ws 的位置
            # 由于timestamps升序、窗口单调递增，idx只需前进跳过 time < ws 的旧行
            while idx < n and rows[idx][2] < ws:
                idx += 1
        # 吸收当前窗口内 time <= t 的所有记录，更新每个code的最新wc
        # 注意：rows按time升序，所以后出现的即更晚 → 直接覆盖
        j = idx
        # 不能移动idx（下一个t可能还在同窗口，需要重新从窗口起点吗？）
        # 优化：由于t单调递增，同窗口内可持续前进idx；跨窗口时上面已重置
        while idx < n and rows[idx][2] <= t and _window_start(rows[idx][2]) == ws:
            code = rows[idx][0]
            window_latest[code] = rows[idx][3]  # 升序，直接覆盖=最新
            idx += 1
        # 若遇到属于更晚窗口的行（rows[idx]的窗口>ws），停在此处，等下个窗口处理
        wc_timeline[t] = dict(window_latest)
    return wc_timeline
