# -*- coding: utf-8 -*-
"""
重算指定日期 apqd 表的 tick_diff 字段（方案2 · 完整历史重算）

背景:
    tick 涨跌差原用 cur_up/cur_down(相对昨收的红绿盘家数) 累加, 普跌/普涨日会单边堆积。
    已修正为 min_up/min_down(相对上一tick的转强/转弱家数)。
    本脚本按新逻辑重算已落库的历史 tick_diff, 同步更新 MySQL 与 Redis。

重算逻辑(与生产 culculate_*_apqd_top30 完全一致):
    按 time 升序遍历每个 tick:
        if min_up > min_down:   acc += 1
        elif min_down > min_up: acc -= 1
        else:                   acc 不变   (含 min_up=min_down=0 的首tick/数据断点)
    每个 tick 的 tick_diff = 当前累加值 acc

数据来源:
    apqd 表已存有每 tick 的 min_up/min_down 列, 无需回读 sssj 巨表。

用法:
    # 默认: 今天日期 + 股债都处理 + 写 MySQL 和 Redis
    python recompute_tick_diff.py
    # 预览(只打印对比, 不写库):
    python recompute_tick_diff.py --dry-run
    # 指定日期:
    python recompute_tick_diff.py --date 20260811
    # 只处理其一:
    python recompute_tick_diff.py --market stock
    python recompute_tick_diff.py --market bond
    # 跳过 Redis(只改 MySQL):
    python recompute_tick_diff.py --no-redis

注意:
    - Redis 中 apqd 数据 key = "{table}:{time}", 值为单行 DataFrame 的 JSON(orient=records, 未压缩)。
      只有仍未过期(EXPIRE_SECONDS)的 tick key 才会被更新; 已过期的自然跳过(不影响, 前端主要读 MySQL 兜底)。
    - 脚本先在内存算好全部新值, MySQL 用单事务批量 UPDATE, 出错回滚。
"""
import argparse
import io
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

from sqlalchemy import text
from gs2026.utils import config_util

try:
    from gs2026.utils import redis_util
    _REDIS_OK = True
except Exception as _e:
    _REDIS_OK = False
    print(f"[warn] redis_util 导入失败, 将只能更新 MySQL: {_e}")


MARKET_TABLE = {
    'stock': 'monitor_gp_apqd_{date}',
    'bond':  'monitor_zq_apqd_{date}',
}


def recompute_one(engine, table_name, dry_run=False, update_redis=True):
    """重算单张 apqd 表的 tick_diff。返回 (改动行数, 总行数)。"""
    # 1. 读取全部 tick(按 time 升序), 只取重算所需字段
    with engine.connect() as conn:
        rows = list(conn.execute(text(
            f"SELECT time, min_up, min_down, tick_diff "
            f"FROM `{table_name}` ORDER BY time ASC"
        )))
    if not rows:
        print(f"[{table_name}] 无数据, 跳过")
        return 0, 0

    # 2. 内存重算 (与生产逻辑完全一致)
    acc = 0
    plan = []  # [(time, old_td, new_td)]
    for r in rows:
        t = r[0]
        mu = int(r[1] or 0)
        md = int(r[2] or 0)
        old_td = int(r[3] or 0)
        if mu > md:
            acc += 1
        elif md > mu:
            acc -= 1
        # else: 不变(含 mu=md=0)
        plan.append((t, old_td, acc))

    changed = [(t, o, n) for (t, o, n) in plan if o != n]

    # 3. 预览输出
    print(f"\n===== [{table_name}] =====")
    print(f"总 tick 数: {len(plan)}, 需改动: {len(changed)}")
    print(f"旧 tick_diff 收盘值: {plan[-1][1]}  ->  新 tick_diff 收盘值: {plan[-1][2]}")
    print("样本(前5改动):")
    for t, o, n in changed[:5]:
        print(f"   {t}: {o} -> {n}")
    if len(changed) > 5:
        print("   ...")
        for t, o, n in changed[-3:]:
            print(f"   {t}: {o} -> {n}")

    if dry_run:
        print(f"[dry-run] 未写库。")
        return len(changed), len(plan)

    # 4. 写 MySQL (单事务批量 UPDATE, 出错回滚)。仅更新有变化的行。
    if changed:
        with engine.begin() as conn:  # begin() 自动 commit/rollback
            for t, o, n in changed:
                conn.execute(
                    text(f"UPDATE `{table_name}` SET tick_diff = :td WHERE time = :t"),
                    {"td": n, "t": t}
                )
        print(f"[MySQL] 已更新 {len(changed)} 行。")
    else:
        print(f"[MySQL] 现值已是最新, 无需更新(幂等)。")

    # 5. 写 Redis (独立于 MySQL changed；用全量 plan 保证一致；只更新仍存在的 tick key)
    if update_redis and _REDIS_OK:
        client = redis_util._get_redis_client()
        if client is None:
            print("[Redis] 客户端未初始化, 跳过 Redis 更新。")
        else:
            r_updated, r_missing, r_skip = 0, 0, 0
            for t, o, n in plan:
                key = f"{table_name}:{t}"
                raw = client.get(key)
                if raw is None:
                    r_missing += 1
                    continue
                try:
                    s = raw.decode('utf-8') if isinstance(raw, (bytes, bytearray)) else raw
                    data = json.loads(s)  # list[dict], apqd 单行
                    # 仅当值不同才写, 减少无谓写入
                    if all(int(rec.get('tick_diff', 0)) == n for rec in data):
                        r_skip += 1
                        continue
                    for rec in data:
                        rec['tick_diff'] = n
                    ttl = client.ttl(key)  # 保留剩余 TTL
                    new_json = json.dumps(data, ensure_ascii=False)
                    if ttl and ttl > 0:
                        client.setex(key, ttl, new_json)
                    else:
                        client.set(key, new_json)
                    r_updated += 1
                except Exception as ex:
                    print(f"   [redis warn] key={key} 更新失败: {ex}")
            print(f"[Redis] 更新 {r_updated} 个 tick key, 已一致跳过 {r_skip} 个, 已过期/不存在 {r_missing} 个。")
    elif update_redis and not _REDIS_OK:
        print("[Redis] redis_util 不可用, 已跳过 Redis 更新。")
    else:
        print("[Redis] --no-redis, 已跳过 Redis 更新。")

    return len(changed), len(plan)


def main():
    import datetime
    _today = datetime.datetime.now().strftime('%Y%m%d')
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=_today, help='日期 YYYYMMDD, 默认今天')
    ap.add_argument('--market', choices=['stock', 'bond', 'both'], default='both')
    ap.add_argument('--dry-run', action='store_true', help='只预览不写库')
    ap.add_argument('--no-redis', action='store_true', help='只改MySQL, 跳过Redis')
    args = ap.parse_args()

    markets = ['stock', 'bond'] if args.market == 'both' else [args.market]
    engine = config_util.get_engine()

    # 初始化 Redis(与 monitor_stock 同源方式)，失败则自动降级为只改 MySQL
    global _REDIS_OK
    if not args.no_redis and _REDIS_OK:
        try:
            redis_host = config_util.get_config('common.redis.host')
            redis_port = config_util.get_config('common.redis.port')
            redis_util.init_redis(host=redis_host, port=redis_port, decode_responses=False)
            print(f"[Redis] 已初始化: {redis_host}:{redis_port}")
        except Exception as ex:
            print(f"[Redis] 初始化失败, 降级为只改 MySQL: {ex}")
            _REDIS_OK = False

    total_changed = 0
    for mk in markets:
        table = MARKET_TABLE[mk].format(date=args.date)
        try:
            c, _ = recompute_one(engine, table, dry_run=args.dry_run,
                                 update_redis=not args.no_redis)
            total_changed += c
        except Exception as ex:
            print(f"[{table}] 处理异常: {ex}")

    print(f"\n===== 完成 =====  dry_run={args.dry_run}  累计改动行数={total_changed}")
    if args.dry_run:
        print("确认无误后, 去掉 --dry-run 重新执行即可写库。")


if __name__ == '__main__':
    main()
