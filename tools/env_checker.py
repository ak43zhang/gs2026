#!/usr/bin/env python3
"""
环境检查工具
检查运行环境、依赖、数据库连接等

使用示例:
    python tools/env_checker.py
    python tools/env_checker.py --check-db
    python tools/env_checker.py --check-redis
"""
import sys
sys.path.insert(0, 'src')

import argparse
import platform
import subprocess


def check_python_version():
    """检查Python版本"""
    print("\n=== Python版本 ===")
    version = platform.python_version()
    print(f"版本: {version}")
    
    major, minor = map(int, version.split('.')[:2])
    if major < 3 or (major == 3 and minor < 8):
        print("⚠️ 建议Python 3.8+")
    else:
        print("✅ 版本符合要求")


def check_dependencies():
    """检查依赖包"""
    print("\n=== 依赖包检查 ===")
    
    required = [
        'flask', 'pandas', 'sqlalchemy', 'pymysql', 'redis',
        'requests', 'pypinyin', 'apscheduler'
    ]
    
    for pkg in required:
        try:
            __import__(pkg)
            print(f"  ✅ {pkg}")
        except ImportError:
            print(f"  ❌ {pkg} (未安装)")


def check_database():
    """检查数据库连接"""
    print("\n=== 数据库连接 ===")
    
    try:
        from gs2026.utils import mysql_util
        mysql_tool = mysql_util.get_mysql_tool()
        
        with mysql_tool.engine.connect() as conn:
            import pandas as pd
            result = pd.read_sql("SELECT VERSION() as version", conn)
            version = result.iloc[0]['version']
            print(f"✅ MySQL连接正常")
            print(f"  版本: {version}")
            
            # 检查关键表
            tables = pd.read_sql("SHOW TABLES", conn)
            table_list = tables.iloc[:, 0].tolist()
            
            key_tables = [
                'cache_stock_industry_concept_bond',
                'data_bond_qs_jsl',
                'data_industry_code_component_ths'
            ]
            
            print(f"\n关键表检查:")
            for t in key_tables:
                status = "✅" if t in table_list else "❌"
                print(f"  {status} {t}")
            
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")


def check_redis():
    """检查Redis连接"""
    print("\n=== Redis连接 ===")
    
    try:
        from gs2026.utils import redis_util
        redis_client = redis_util.get_redis_client()
        
        info = redis_client.info('server')
        print(f"✅ Redis连接正常")
        print(f"  版本: {info.get('redis_version', 'N/A')}")
        print(f"  模式: {info.get('redis_mode', 'N/A')}")
        
        # 检查内存
        mem = redis_client.info('memory')
        used = mem.get('used_memory_human', 'N/A')
        print(f"  内存使用: {used}")
        
    except Exception as e:
        print(f"❌ Redis连接失败: {e}")


def check_flask_app():
    """检查Flask应用"""
    print("\n=== Flask应用 ===")
    
    try:
        import requests
        resp = requests.get('http://localhost:8080/', timeout=5)
        print(f"✅ 应用运行中 (状态码: {resp.status_code})")
    except:
        print("❌ 应用未运行或端口8080未监听")


def main():
    parser = argparse.ArgumentParser(description='环境检查工具')
    parser.add_argument('--check-db', action='store_true', help='检查数据库')
    parser.add_argument('--check-redis', action='store_true', help='检查Redis')
    parser.add_argument('--check-app', action='store_true', help='检查应用')
    
    args = parser.parse_args()
    
    if args.check_db:
        check_database()
    elif args.check_redis:
        check_redis()
    elif args.check_app:
        check_flask_app()
    else:
        # 全部检查
        check_python_version()
        check_dependencies()
        check_database()
        check_redis()
        check_flask_app()


if __name__ == '__main__':
    main()
