"""
MySQL monitor table archiver - split parquet by size

Structure: output_dir/{table_name}/part_001.parquet, part_002.parquet, ...
Each part targets ~128MB (configurable).
"""
import os, re, time, argparse, json
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import create_engine, text

DB_URI = 'mysql+pymysql://root:123456@192.168.0.101:3306/gs'
DEFAULT_OUTPUT = r'D:\gsdata2\mysql_achieve'
DEFAULT_DAYS = 30
TARGET_PART_MB = 128  # target size per parquet part

ARCHIVE_PREFIXES = [
    'monitor_gp_sssj_', 'monitor_zq_sssj_', 'monitor_hy_sssj_',
    'monitor_gp_top30_', 'monitor_zq_top30_', 'monitor_hy_top30_',
    'monitor_gp_apqd_', 'monitor_zq_apqd_', 'monitor_hy_apqd_',
    'monitor_combine_', 'monitor_dp_signal_', 'monitor_gp_zq_rising_signal_',
]

DATE_RE = re.compile(r'(\d{8})$')


def parse_table_date(name):
    m = DATE_RE.search(name)
    if m:
        try:
            return datetime.strptime(m.group(1), '%Y%m%d').date()
        except ValueError:
            pass
    return None


def get_archivable_tables(engine, days):
    cutoff = (datetime.now() - timedelta(days=days)).date()
    tables = []
    with engine.connect() as conn:
        r = conn.execute(text(
            "SELECT table_name, "
            "ROUND((data_length + index_length)/1024/1024, 1) AS size_mb, "
            "table_rows "
            "FROM information_schema.TABLES WHERE table_schema='gs' ORDER BY table_name"
        ))
        for row in r.fetchall():
            tbl, size_mb, rows = row[0], float(row[1]), int(row[2] or 0)
            if not any(tbl.startswith(p) for p in ARCHIVE_PREFIXES):
                continue
            dt = parse_table_date(tbl)
            if dt and dt < cutoff:
                tables.append({'name': tbl, 'date': dt, 'size_mb': size_mb, 'rows': rows})
    tables.sort(key=lambda x: x['name'])
    return tables


def estimate_chunk_rows(engine, table_name, table_size_mb, target_mb=TARGET_PART_MB):
    """Estimate rows per chunk to hit target parquet size"""
    with engine.connect() as conn:
        r = conn.execute(text(f"SELECT COUNT(*) FROM `{table_name}`"))
        total_rows = r.fetchone()[0]
    if total_rows == 0 or table_size_mb == 0:
        return total_rows, total_rows  # single chunk
    # parquet is ~3-5x smaller than MySQL, so estimate parquet size
    est_parquet_mb = table_size_mb / 4.0
    num_parts = max(1, int(est_parquet_mb / target_mb))
    chunk_rows = max(10000, total_rows // num_parts)
    return total_rows, chunk_rows


def archive_table_split(engine, table_name, output_dir, target_mb=TARGET_PART_MB):
    """Archive one table into directory with split parquet files"""
    table_dir = os.path.join(output_dir, table_name)

    # Check if already archived
    meta_path = os.path.join(table_dir, '_meta.json')
    if os.path.exists(meta_path):
        with open(meta_path, 'r') as f:
            meta = json.load(f)
        print(f"    Already archived ({meta['total_rows']} rows, {meta['num_parts']} parts), skip")
        return meta['total_rows'], True

    os.makedirs(table_dir, exist_ok=True)

    # Get exact row count and estimate chunk size
    with engine.connect() as conn:
        r = conn.execute(text(f"SELECT COUNT(*) FROM `{table_name}`"))
        total_rows = r.fetchone()[0]

    if total_rows == 0:
        # Write empty meta
        meta = {'table': table_name, 'total_rows': 0, 'num_parts': 0, 'parts': []}
        with open(meta_path, 'w') as f:
            json.dump(meta, f, indent=2)
        print(f"    Empty table, skip")
        return 0, True

    # Get table size for chunk estimation
    with engine.connect() as conn:
        r = conn.execute(text(
            f"SELECT ROUND((data_length+index_length)/1024/1024,1) "
            f"FROM information_schema.TABLES "
            f"WHERE table_schema='gs' AND table_name='{table_name}'"
        ))
        table_size_mb = float(r.fetchone()[0])

    est_parquet_mb = table_size_mb / 4.0
    num_parts = max(1, int(est_parquet_mb / target_mb + 0.5))
    chunk_rows = max(10000, total_rows // num_parts)

    t0 = time.time()
    parts = []
    rows_written = 0
    part_idx = 0

    with engine.connect() as conn:
        for chunk_df in pd.read_sql(f"SELECT * FROM `{table_name}`", conn, chunksize=chunk_rows):
            part_idx += 1
            part_name = f"part_{part_idx:03d}.parquet"
            part_path = os.path.join(table_dir, part_name)
            chunk_df.to_parquet(part_path, compression='snappy', index=False)
            part_size = os.path.getsize(part_path) / 1024 / 1024
            parts.append({
                'file': part_name,
                'rows': len(chunk_df),
                'size_mb': round(part_size, 2)
            })
            rows_written += len(chunk_df)
            print(f"    part {part_idx}: {len(chunk_df)} rows, {part_size:.1f} MB", flush=True)

    elapsed = time.time() - t0
    total_pq_mb = sum(p['size_mb'] for p in parts)

    # Write metadata
    meta = {
        'table': table_name,
        'total_rows': rows_written,
        'mysql_rows': total_rows,
        'mysql_size_mb': table_size_mb,
        'parquet_size_mb': round(total_pq_mb, 2),
        'compression_ratio': round(table_size_mb / total_pq_mb, 1) if total_pq_mb > 0 else 0,
        'num_parts': len(parts),
        'target_part_mb': target_mb,
        'parts': parts,
        'archived_at': datetime.now().isoformat(),
        'elapsed_seconds': round(elapsed, 1)
    }
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print(f"    Total: {rows_written} rows -> {len(parts)} parts, "
          f"{total_pq_mb:.1f} MB parquet ({table_size_mb:.0f} MB MySQL, "
          f"{meta['compression_ratio']}x), {elapsed:.0f}s")

    return rows_written, rows_written == total_rows


def verify_archive(table_dir, expected_rows):
    """Verify all parts in a table directory"""
    meta_path = os.path.join(table_dir, '_meta.json')
    if not os.path.exists(meta_path):
        return False, "no _meta.json"

    with open(meta_path, 'r') as f:
        meta = json.load(f)

    total = 0
    for p in meta['parts']:
        pq_path = os.path.join(table_dir, p['file'])
        if not os.path.exists(pq_path):
            return False, f"missing {p['file']}"
        df = pd.read_parquet(pq_path)
        if len(df) != p['rows']:
            return False, f"{p['file']}: expected {p['rows']} got {len(df)}"
        total += len(df)

    if total != expected_rows:
        return False, f"total rows {total} != expected {expected_rows}"

    return True, f"OK ({total} rows, {len(meta['parts'])} parts)"


def drop_table(engine, table_name):
    with engine.connect() as conn:
        conn.execute(text(f"DROP TABLE `{table_name}`"))
        conn.commit()


def scan(engine, days):
    tables = get_archivable_tables(engine, days)
    if not tables:
        print("No tables to archive (all within %d days)" % days)
        return []
    total_mb = sum(t['size_mb'] for t in tables)
    print("=" * 75)
    print("Tables to archive (older than %d days, before %s):" % (
        days, (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')))
    print("=" * 75)
    for t in tables:
        print("  %-50s %8.1f MB %10d rows  %s" % (t['name'], t['size_mb'], t['rows'], t['date']))
    print("-" * 75)
    print("  Total: %d tables, %.1f GB" % (len(tables), total_mb / 1024))
    return tables


def archive(engine, days, output_dir, auto_yes=False):
    os.makedirs(output_dir, exist_ok=True)
    tables = scan(engine, days)
    if not tables:
        return

    if not auto_yes:
        ans = input("\nArchive and DROP %d tables? [y/N] " % len(tables))
        if ans.strip().lower() != 'y':
            print("Cancelled")
            return

    ok, fail, skip = 0, 0, 0
    freed_mb = 0
    t0 = time.time()

    for i, t in enumerate(tables, 1):
        print("\n[%d/%d] %s (%.1f MB, %d rows)" % (i, len(tables), t['name'], t['size_mb'], t['rows']))
        try:
            rows, match = archive_table_split(engine, t['name'], output_dir)
            if not match:
                print("    FAIL: row count mismatch, skip DROP")
                fail += 1
                continue

            # Verify
            table_dir = os.path.join(output_dir, t['name'])
            with engine.connect() as conn:
                r = conn.execute(text(f"SELECT COUNT(*) FROM `{t['name']}`"))
                exact = r.fetchone()[0]

            valid, msg = verify_archive(table_dir, exact)
            if not valid:
                print(f"    FAIL verify: {msg}, skip DROP")
                fail += 1
                continue

            # DROP
            drop_table(engine, t['name'])
            print(f"    DROP TABLE done")
            ok += 1
            freed_mb += t['size_mb']

        except Exception as e:
            print(f"    ERROR: {e}")
            fail += 1

    elapsed = time.time() - t0
    print("\n" + "=" * 75)
    print("Done: ok=%d fail=%d freed=%.1f GB elapsed=%.0fs" % (ok, fail, freed_mb / 1024, elapsed))


def main():
    parser = argparse.ArgumentParser(description='MySQL monitor table archiver (split parquet)')
    parser.add_argument('--scan', action='store_true')
    parser.add_argument('--archive', action='store_true')
    parser.add_argument('--days', type=int, default=DEFAULT_DAYS)
    parser.add_argument('--output', default=DEFAULT_OUTPUT)
    parser.add_argument('--part-mb', type=int, default=TARGET_PART_MB)
    parser.add_argument('--yes', '-y', action='store_true')
    args = parser.parse_args()

    engine = create_engine(DB_URI)
    if args.archive:
        archive(engine, args.days, args.output, args.yes)
    else:
        scan(engine, args.days)


if __name__ == '__main__':
    main()
