"""Check monitor.html for tab buttons"""
with open(r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Print lines 1066-1080
print("=== Lines 1066-1080 ===")
for i in range(1065, min(1080, len(lines))):
    # escape non-ascii
    safe = lines[i].encode('ascii', 'replace').decode()
    print(f"L{i+1}: {safe.rstrip()}")

print("\n=== Search results ===")
print(f"bp-tab-btn found: {'bp-tab-btn' in ''.join(lines)}")
print(f"switchBpTab found: {'switchBpTab' in ''.join(lines)}")
print(f"quant-screen-section found: {'quant-screen-section' in ''.join(lines)}")

# Find buy-points-panel line
for i, l in enumerate(lines):
    if 'buy-points-panel' in l:
        print(f"\nbuy-points-panel at line {i+1}")
        for j in range(i, min(i+8, len(lines))):
            safe = lines[j].encode('ascii', 'replace').decode()
            print(f"  L{j+1}: {safe.rstrip()}")
        break
