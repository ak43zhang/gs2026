"""
切换到后端过滤

运行: python switch_to_backend.py
"""
import requests
import json


def switch_mode(use_backend):
    """切换过滤模式"""
    url = 'http://localhost:5000/api/filter/config'
    
    try:
        response = requests.post(url, json={
            'USE_BACKEND_FILTER': use_backend
        })
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ {result['message']}")
            return True
        else:
            print(f"❌ 切换失败: HTTP {response.status_code}")
            print(response.text)
            return False
            
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False


def main():
    """主函数"""
    print("="*60)
    print("过滤模式切换")
    print("="*60)
    
    import sys
    if len(sys.argv) < 2:
        print("\n用法: python switch_to_backend.py [on|off]")
        print("  on  - 切换到后端过滤")
        print("  off - 切换到前端过滤")
        return
    
    mode = sys.argv[1].lower()
    
    if mode == 'on':
        print("\n切换到后端过滤...")
        if switch_mode(True):
            print("\n✅ 切换成功")
            print("\n监控指标:")
            print("  - 错误率 < 0.1%")
            print("  - 响应时间 < 200ms")
            print("\n回滚命令:")
            print("  python switch_to_backend.py off")
    elif mode == 'off':
        print("\n切换到前端过滤...")
        if switch_mode(False):
            print("\n✅ 回退成功")
    else:
        print(f"❌ 无效参数: {mode}")


if __name__ == '__main__':
    main()
