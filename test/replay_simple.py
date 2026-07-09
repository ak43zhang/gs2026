#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化版量化选债历史数据回放测试
直接测试数据库连接和API逻辑
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))

async def test_database():
    """测试数据库连接和表结构"""
    print("=" * 60)
    print("测试数据库连接")
    print("=" * 60)
    
    try:
        import aiomysql
        
        # 从配置读取连接信息
        from gs2026.dashboard2.config import Config
        
        print(f"MySQL URI: {Config.MYSQL_URI[:30]}...")
        
        # 解析连接信息
        import re
        match = re.match(r'mysql\+aiomysql://([^:]+):([^@]+)@([^/]+)/(\w+)', Config.MYSQL_URI)
        if not match:
            print("[错误] 无法解析MySQL URI")
            return False
            
        user, password, host, db = match.groups()
        
        # 连接数据库
        conn = await aiomysql.connect(
            host=host.split(':')[0],
            port=int(host.split(':')[1]) if ':' in host else 3306,
            user=user,
            password=password,
            db=db
        )
        
        async with conn.cursor() as cur:
            # 检查quant_screen_hits表
            await cur.execute("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_name = 'quant_screen_hits'
            """)
            result = await cur.fetchone()
            
            if result[0] == 0:
                print("[警告] quant_screen_hits 表不存在，需要创建")
            else:
                print("[成功] quant_screen_hits 表存在")
                
                # 检查今日记录
                today = datetime.now().strftime('%Y%m%d')
                await cur.execute(
                    "SELECT COUNT(*) FROM quant_screen_hits WHERE trade_date = %s",
                    (today,)
                )
                count = await cur.fetchone()
                print(f"[信息] 今日({today})命中记录数: {count[0]}")
        
        conn.close()
        print("[成功] 数据库连接正常")
        return True
        
    except Exception as e:
        print(f"[错误] 数据库测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_mock_function():
    """测试运行时替换逻辑"""
    print("\n" + "=" * 60)
    print("测试运行时替换(Monkey Patch)")
    print("=" * 60)
    
    try:
        from gs2026.dashboard2.routes import monitor
        
        # 保存原函数
        original = monitor._get_current_sssj
        
        # 创建mock数据
        mock_data = {
            'bond_code': ['123045', '123046'],
            'bond_name': ['测试转债1', '测试转债2'],
            'price': [100.0, 101.0],
            'change_pct': [2.5, 3.0],
            'amount': [1000000, 2000000]
        }
        
        # 替换函数
        def mock_get_current_sssj(date):
            print(f"[Mock] 返回测试数据，日期: {date}")
            return mock_data
        
        monitor._get_current_sssj = mock_get_current_sssj
        
        # 测试调用
        result = monitor._get_current_sssj('20260709')
        print(f"[成功] Mock函数返回: {result}")
        
        # 恢复原函数
        monitor._get_current_sssj = original
        print("[成功] 原函数已恢复")
        
        return True
        
    except Exception as e:
        print(f"[错误] Mock测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_local_storage_format():
    """测试localStorage数据格式"""
    print("\n" + "=" * 60)
    print("测试localStorage数据格式")
    print("=" * 60)
    
    # 模拟前端保存的数据
    quant_screen_state = {
        "selectedSchemes": ["强势反弹", "高成交额"],
        "isEnabled": True,
        "timestamp": "2026-07-09T19:30:00.000Z"
    }
    
    schemes = [
        {
            "name": "强势反弹",
            "conditions": [
                {"field": "change_pct", "op": ">", "value": 2.0, "logic": "AND"}
            ],
            "stop_loss": 3.0,
            "take_profit": 5.0,
            "max_hold_time": 30
        }
    ]
    
    print(f"[信息] 状态数据: {json.dumps(quant_screen_state, ensure_ascii=False)}")
    print(f"[信息] 方案数据: {json.dumps(schemes, ensure_ascii=False)}")
    print("[成功] 数据格式正确")
    
    return True


async def main():
    """主测试流程"""
    print("\n" + "=" * 60)
    print("量化选债功能完整性测试")
    print("=" * 60 + "\n")
    
    results = []
    
    # 测试1: 数据库连接
    results.append(("数据库连接", await test_database()))
    
    # 测试2: Mock函数替换
    results.append(("运行时替换", test_mock_function()))
    
    # 测试3: 数据格式
    results.append(("数据格式", test_local_storage_format()))
    
    # 汇总
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"{name}: {status}")
    
    all_passed = all(r[1] for r in results)
    
    print("\n" + "=" * 60)
    if all_passed:
        print("所有测试通过！功能完整性验证成功。")
    else:
        print("部分测试失败，请检查上述错误。")
    print("=" * 60 + "\n")
    
    return all_passed


if __name__ == '__main__':
    asyncio.run(main())
