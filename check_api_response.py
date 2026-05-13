"""检查API响应详情"""
import requests

url = 'http://localhost:8080/api/monitor/attack-ranking/stock?limit=60'
print(f"Testing: {url}")
try:
    response = requests.get(url, timeout=30)
    print(f"Status: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type')}")
    print(f"Length: {len(response.text)}")
    
    # Check first 500 chars
    preview = response.text[:500]
    print(f"\nPreview:\n{preview}")
    
    # Try to parse as JSON
    try:
        data = response.json()
        print(f"\nJSON parsed successfully!")
        print(f"success: {data.get('success')}")
        print(f"count: {data.get('count')}")
        if data.get('data'):
            print(f"First item: {data['data'][0]}")
    except:
        print(f"\nNot JSON - likely HTML error page")
except Exception as e:
    print(f"Error: {e}")
