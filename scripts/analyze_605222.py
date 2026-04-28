#!/usr/bin/env python3
"""605222 深度分析"""
from sqlalchemy import create_engine, text
import pandas as pd

engine = create_engine('mysql+pymysql://root:123456@192.168.0.101:3306/gs')

with engine.connect() as conn:
    # 全量数据
    df = pd.read_sql("""
        SELECT time, price, change_pct, volume, amount,
               main_net_amount, main_behavior, main_confidence
        FROM monitor_gp_sssj_20260428
        WHERE stock_code = '002297'
        ORDER BY time
    """, conn)

df['price'] = pd.to_numeric(df['price'], errors='coerce')
df['change_pct'] = pd.to_numeric(df['change_pct'], errors='coerce')
df['main_net_amount'] = pd.to_numeric(df['main_net_amount'], errors='coerce')

print("=== 605222 Deep Analysis ===")
print(f"Total records: {len(df)}")
print(f"Records with net!=0: {(df['main_net_amount'] != 0).sum()}")
print()

# 价格走势关键点
print("=== Price Timeline ===")
key_times = ['09:30:00','09:35:00','09:40:00','09:45:00','09:50:00','09:55:00',
             '10:00:00','10:15:00','10:30:00','10:45:00','11:00:00','11:15:00','11:30:00',
             '13:00:00','13:15:00','13:30:00','13:45:00','14:00:00','14:15:00','14:30:00',
             '14:45:00','14:57:00']
for t in key_times:
    row = df[df['time'] >= t].head(1)
    if not row.empty:
        r = row.iloc[0]
        print(f"  {r['time']}: price={r['price']:.2f}, chg={r['change_pct']:>+6.2f}%")
print()

# 按30分钟时段统计
print("=== 30-min Period Stats ===")
periods = [
    ('09:30', '10:00', 'AM open'),
    ('10:00', '10:30', 'AM mid-1'),
    ('10:30', '11:00', 'AM mid-2'),
    ('11:00', '11:30', 'AM close'),
    ('13:00', '13:30', 'PM open'),
    ('13:30', '14:00', 'PM mid-1'),
    ('14:00', '14:30', 'PM mid-2'),
    ('14:30', '15:00', 'PM close'),
]

df_main = df[df['main_net_amount'] != 0].copy()
print(f"{'Period':<20} {'Net':>14} {'Buy#':>5} {'Sell#':>5} {'BigBuy':>5} {'BigSell':>5} {'Price range'}")
print("-" * 95)

for start, end, label in periods:
    mask = (df_main['time'] >= start + ':00') & (df_main['time'] < end + ':00')
    period = df_main[mask]
    if period.empty:
        print(f"  {start}-{end} {label:<12} {'(no data)':>14}")
        continue
    
    net = period['main_net_amount'].sum()
    buy_cnt = (period['main_net_amount'] > 0).sum()
    sell_cnt = (period['main_net_amount'] < 0).sum()
    big_buy = (period['main_behavior'] == 'da_buy').sum()
    big_sell = (period['main_behavior'] == 'da_sell').sum()
    
    # 对应时段价格
    pmask = (df['time'] >= start + ':00') & (df['time'] < end + ':00')
    pdf = df[pmask]
    if not pdf.empty:
        p_start = pdf['price'].iloc[0]
        p_end = pdf['price'].iloc[-1]
        p_high = pdf['price'].max()
        p_low = pdf['price'].min()
        price_info = f"{p_start:.2f}->{p_end:.2f} (H:{p_high:.2f} L:{p_low:.2f})"
    else:
        price_info = ""
    
    print(f"  {start}-{end} {label:<12} {net:>13,.0f} {buy_cnt:>5} {sell_cnt:>5} {big_buy:>5} {big_sell:>5}   {price_info}")

print()

# 大额交易详情
print("=== Large Trades (da_buy / da_sell) ===")
da = df_main[df_main['main_behavior'].isin(['da_buy', 'da_sell'])].copy()
if not da.empty:
    print(f"{'time':<12} {'price':>7} {'chg%':>7} {'net_amount':>14} {'behavior':<12} {'conf':>5}")
    print("-" * 65)
    for _, r in da.head(30).iterrows():
        print(f"{r['time']:<12} {r['price']:>7.2f} {r['change_pct']:>+6.2f}% {r['main_net_amount']:>13,.0f} {r['main_behavior']:<12} {r['main_confidence']:.2f}")
    if len(da) > 30:
        print(f"  ... ({len(da)} total, showing first 30)")
print()

# 累计净额曲线（采样）
print("=== Cumulative Net Amount (sampled) ===")
df['cum_net'] = df['main_net_amount'].cumsum()
sample_times = ['09:30:00','09:40:00','09:50:00','10:00:00','10:30:00','11:00:00','11:30:00',
                '13:00:00','13:30:00','14:00:00','14:30:00','14:57:00']
for t in sample_times:
    row = df[df['time'] >= t].head(1)
    if not row.empty:
        r = row.iloc[0]
        print(f"  {r['time']}: cum_net={r['cum_net']:>14,.0f}  price={r['price']:.2f}")
print()

# 买卖力量对比
total_buy = df_main[df_main['main_net_amount'] > 0]['main_net_amount'].sum()
total_sell = df_main[df_main['main_net_amount'] < 0]['main_net_amount'].abs().sum()
ratio = total_buy / total_sell if total_sell > 0 else float('inf')
print(f"=== Buy/Sell Power ===")
print(f"Total buy amount:  {total_buy:>14,.0f}")
print(f"Total sell amount: {total_sell:>14,.0f}")
print(f"Buy/Sell ratio:    {ratio:.2f}")
print()
print("[DONE]")
