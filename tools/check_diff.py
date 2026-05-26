import subprocess

# Get diff stats for key files
files = [
    'src/gs2026/dashboard2/routes/monitor.py',
    'src/gs2026/dashboard2/routes/profile.py', 
    'src/gs2026/dashboard2/core/blueprint_registry.py',
    'src/gs2026/dashboard/services/data_service.py',
    'src/gs2026/dashboard2/services/stock_picker_service.py',
    'src/gs2026/monitor/monitor_bond.py',
    'src/gs2026/monitor/monitor_stock.py',
]

for f in files:
    try:
        result = subprocess.run(['git', 'diff', '--stat', f], 
                              capture_output=True, text=True, encoding='utf-8', errors='ignore')
        if result.stdout.strip():
            print(f"\n=== {f} ===")
            print(result.stdout)
    except Exception as e:
        print(f"Error checking {f}: {e}")
