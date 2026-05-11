# -*- coding: utf-8 -*-
"""诊断并发抓取失败原因"""
import sys, time, threading, requests
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')
from gs2026.utils import config_util

API_URL = 'https://np-cnotice-stock.eastmoney.com/api/content/ann'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://data.eastmoney.com/'
}

# 用一个已知有效的 art_code
TEST_CODE = 'AN202604301821789162'

def test_single():
    """单线程测试"""
    print('=== 单线程测试 ===')
    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        r = s.get(API_URL, params={'art_code': TEST_CODE, 'client_source': 'web', 'page_index': 1}, timeout=10)
        print(f'  Status: {r.status_code}')
        data = r.json().get('data', {})
        content = (data.get('notice_content') or '')[:80]
        print(f'  Content: {content}...')
        print(f'  OK!')
    except Exception as e:
        print(f'  FAILED: {type(e).__name__}: {e}')
    s.close()

def test_concurrent(n, delay=0.0):
    """并发测试"""
    print(f'\n=== {n}线程并发测试 (delay={delay}s) ===')
    results = []
    
    def worker(idx):
        time.sleep(delay * idx)  # stagger
        s = requests.Session()
        s.headers.update(HEADERS)
        try:
            r = s.get(API_URL, params={'art_code': TEST_CODE, 'client_source': 'web', 'page_index': 1}, timeout=10)
            results.append((idx, r.status_code, None))
        except Exception as e:
            results.append((idx, 0, f'{type(e).__name__}: {e}'))
        finally:
            s.close()
    
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    t0 = time.time()
    for t in threads: t.start()
    for t in threads: t.join()
    elapsed = time.time() - t0
    
    ok = sum(1 for r in results if r[1] == 200)
    fail = sum(1 for r in results if r[1] != 200)
    print(f'  耗时: {elapsed:.2f}s, 成功: {ok}, 失败: {fail}')
    for idx, status, err in sorted(results):
        if err:
            print(f'  Thread-{idx}: FAIL - {err}')
        else:
            print(f'  Thread-{idx}: HTTP {status}')

# 执行测试
test_single()
test_concurrent(2, delay=0.0)
test_concurrent(4, delay=0.0)
test_concurrent(8, delay=0.0)
test_concurrent(8, delay=0.1)  # 带错峰
test_concurrent(4, delay=0.2)  # 更大错峰
print('\ndone')
