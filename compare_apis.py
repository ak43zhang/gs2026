"""对比股票和债券API"""
import requests
import time

urls = [
    ('stock', 'http://localhost:8080/api/monitor/attack-ranking/stock?limit=60'),
    ('bond', 'http://localhost:8080/api/monitor/attack-ranking/bond?limit=60'),
    ('industry', 'http://localhost:8080/api/monitor/attack-ranking/industry?limit=60'),
]

for name, url in urls:
    print(f"\n{'='*50}")
    print(f"Test {name}: {url}")
    start = time.time()
    try:
        response = requests.get(url, timeout=30)
        elapsed = time.time() - start
        print(f"Status: {response.status_code}, Time: {elapsed:.2f}s")
        
        # Check if JSON
        content_type = response.headers.get('Content-Type', '')
        print(f"Content-Type: {content_type}")
        
        if 'json' in content_type:
            data = response.json()
            print(f"[OK] JSON response")
            print(f"  success: {data.get('success')}")
            print(f"  count: {data.get('count')}")
        else:
            print(f"[FAIL] Not JSON: {response.text[:100]}")
    except Exception as e:
        print(f"[ERROR] {e}")
