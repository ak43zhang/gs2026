def _find_nearest_price(prices, signal_time, offset_min):
    """在sssj价格序列中找 signal_time + offset_min 最近的涨跌幅"""
    sig_sec = _time_to_seconds(signal_time)
    target_sec = sig_sec + offset_min * 60
    # 午休调整: 11:30(41400) ~ 13:00(46800)
    if 41400 < target_sec < 46800:
        target_sec = 46800 + (target_sec - 41400)
    best_change_pct = None
    best_diff = 999999
    for ts, price, change_pct in prices:
        diff = abs(ts - target_sec)
        if diff < best_diff and diff < 300:
            best_diff = diff
            best_change_pct = change_pct
    return best_change_pct

def _find_close_price(prices):
    """取最后一条的涨跌幅作为收盘涨跌幅"""
    if not prices:
        return None
    # 返回最后一条的 change_pct
    return prices[-1][2] if len(prices[-1]) > 2 else None
