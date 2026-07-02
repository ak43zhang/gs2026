"""性能测试 anomaly list 查询"""
from sqlalchemy import text
from gs2026.utils import config_util
import time

engine = config_util.get_engine()
with engine.connect() as conn:
    # 测试全量(含ai_analysis)
    t1 = time.time()
    rows = conn.execute(text(
        "SELECT id, trading_date, stock_code, stock_name, anomaly_type, "
        "anomaly_time, price, change_pct, continuous_zt, "
        "ai_analysis, ai_status, related_industries, related_concepts, "
        "pre_forecast_messages, forecast_match, forecast_note, "
        "mainline_names, created_at "
        "FROM stock_anomaly "
        "WHERE trading_date = CURDATE() AND stock_name NOT LIKE '%ST%' "
        "ORDER BY anomaly_time DESC"
    )).fetchall()
    t2 = time.time()
    print(f"全量{len(rows)}行(含ai_analysis): {(t2-t1)*1000:.0f}ms")

    # ai_analysis大小统计
    sizes = [len(str(r[9])) if r[9] else 0 for r in rows]
    avg_size = sum(sizes) / len(sizes) if sizes else 0
    max_size = max(sizes) if sizes else 0
    non_null = sum(1 for s in sizes if s > 0)
    print(f"ai_analysis: 非空{non_null}条, 平均{avg_size:.0f}字节, 最大{max_size}字节")

    # 测试全量(无ai_analysis)
    t3 = time.time()
    rows2 = conn.execute(text(
        "SELECT id, trading_date, stock_code, stock_name, anomaly_type, "
        "anomaly_time, price, change_pct, continuous_zt, "
        "ai_status, related_industries, related_concepts, "
        "pre_forecast_messages, forecast_match, forecast_note, "
        "mainline_names, created_at "
        "FROM stock_anomaly "
        "WHERE trading_date = CURDATE() AND stock_name NOT LIKE '%ST%' "
        "ORDER BY anomaly_time DESC"
    )).fetchall()
    t4 = time.time()
    print(f"全量{len(rows2)}行(无ai_analysis): {(t4-t3)*1000:.0f}ms")

    # LIMIT 50 分页
    t5 = time.time()
    rows3 = conn.execute(text(
        "SELECT id, trading_date, stock_code, stock_name, anomaly_type, "
        "anomaly_time, price, change_pct, continuous_zt, "
        "ai_analysis, ai_status, related_industries, related_concepts, "
        "pre_forecast_messages, forecast_match, forecast_note, "
        "mainline_names, created_at "
        "FROM stock_anomaly "
        "WHERE trading_date = CURDATE() AND stock_name NOT LIKE '%ST%' "
        "ORDER BY anomaly_time DESC LIMIT 50"
    )).fetchall()
    t6 = time.time()
    print(f"LIMIT 50(含ai_analysis): {(t6-t5)*1000:.0f}ms")
