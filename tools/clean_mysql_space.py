"""
MySQL空间清理脚本 - 安全逐步释放空间
"""
import pymysql
import sys
import time

def clean_space():
    try:
        print("正在连接MySQL...")
        conn = pymysql.connect(
            host='192.168.0.101',
            port=3306,
            user='root',
            password='123456',
            database='gs',
            connect_timeout=10,
            read_timeout=30,
            write_timeout=30
        )
        cursor = conn.cursor()
        
        # 1. 检查当前binlog状态
        print("\n=== 1. 检查binlog状态 ===")
        cursor.execute("SHOW BINARY LOGS")
        logs = cursor.fetchall()
        total_size_mb = 0
        old_logs = []
        
        for log in logs:
            name, size = log[0], log[1]
            size_mb = size / (1024 * 1024)
            total_size_mb += size_mb
            
            # 提取日期（假设文件名包含日期，如 mysql-bin.000123）
            # 或者通过文件修改时间判断
            old_logs.append(name)
            print(f"  {name}: {size_mb:.1f} MB")
        
        print(f"\n总binlog大小: {total_size_mb:.1f} MB ({total_size_mb/1024:.2f} GB)")
        
        # 2. 尝试清理到指定binlog之前（保留最近1-2个）
        if len(old_logs) >= 3:
            # 保留最后2个，删除之前的
            keep_logs = old_logs[-2:]  # 保留最近2个
            purge_to = old_logs[-3]    # 清理到这个文件之前
            
            print(f"\n=== 2. 清理binlog ===")
            print(f"保留: {keep_logs}")
            print(f"清理到: {purge_to} 之前")
            
            try:
                cursor.execute(f"PURGE BINARY LOGS TO '{purge_to}'")
                conn.commit()
                print("✅ binlog清理成功")
            except Exception as e:
                print(f"⚠️ binlog清理失败: {e}")
                print("尝试其他方法...")
        
        # 3. 检查表占用空间
        print("\n=== 3. 检查目标表大小 ===")
        tables_to_drop = [
            'monitor_gp_sssj_20260309',
            'monitor_gp_sssj_20260310',
            'monitor_gp_sssj_20260311'
        ]
        
        total_table_size_mb = 0
        for table in tables_to_drop:
            try:
                cursor.execute(f"""
                    SELECT 
                        ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 2) AS size_mb
                    FROM information_schema.TABLES 
                    WHERE TABLE_SCHEMA = 'gs' AND TABLE_NAME = '{table}'
                """)
                result = cursor.fetchone()
                if result and result[0]:
                    size_mb = result[0]
                    total_table_size_mb += size_mb
                    print(f"  {table}: {size_mb} MB")
                else:
                    print(f"  {table}: 表不存在或无法获取大小")
            except Exception as e:
                print(f"  {table}: 查询失败 - {e}")
        
        print(f"\n可释放空间: {total_table_size_mb} MB ({total_table_size_mb/1024:.2f} GB)")
        
        # 4. 尝试删除表
        print(f"\n=== 4. 删除旧表 ===")
        for table in tables_to_drop:
            try:
                print(f"正在删除 {table}...")
                cursor.execute(f"DROP TABLE IF EXISTS {table}")
                conn.commit()
                print(f"✅ 已删除: {table}")
                time.sleep(0.5)  # 短暂停顿
            except Exception as e:
                print(f"❌ 删除失败 {table}: {e}")
                # 如果失败，可能是磁盘满，尝试继续下一个
                continue
        
        # 5. 最终状态
        print(f"\n=== 5. 清理完成 ===")
        cursor.execute("SHOW BINARY LOGS")
        remaining_logs = cursor.fetchall()
        remaining_size = sum(log[1] for log in remaining_logs) / (1024 * 1024)
        print(f"剩余binlog: {len(remaining_logs)} 个文件, {remaining_size:.1f} MB")
        
        cursor.close()
        conn.close()
        print("\n✅ 操作完成")
        
    except pymysql.err.OperationalError as e:
        print(f"❌ MySQL连接失败: {e}")
        if "Disk full" in str(e) or "28" in str(e):
            print("\n磁盘已满！需要手动清理：")
            print("1. SSH登录到MySQL服务器")
            print("2. 执行: find /var/lib/mysql -name 'mysql-bin.0*' -mtime +1 | head -20")
            print("3. 在MySQL客户端执行: PURGE BINARY LOGS BEFORE DATE_SUB(NOW(), INTERVAL 1 DAY)")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    clean_space()
