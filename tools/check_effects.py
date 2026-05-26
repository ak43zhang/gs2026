import sys, traceback
sys.stdout.reconfigure(encoding='utf-8')

MONITOR_HTML = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\templates\monitor.html'
MONITOR_PY = r'F:\pyworkspace2026\gs2026\src\gs2026\dashboard2\routes\monitor.py'

# ============ Part 1: Verify backend ============
with open(MONITOR_PY, 'r', encoding='utf-8') as f:
    py = f.read()

print('=== Backend ===')
print('generate-effects:', 'generate-effects' in py)
print('find_nearest_price:', 'find_nearest_price' in py)
print('_time_to_seconds:', '_time_to_seconds' in py)

# ============ Part 2: Verify frontend ============
with open(MONITOR_HTML, 'r', encoding='utf-8') as f:
    html = f.read()

print()
print('=== Frontend ===')
print('showEffectPanel:', 'showEffectPanel' in html)
print('generateEffects:', 'generateEffects()' in html)
print('bp-effect-overlay:', 'bp-effect-overlay' in html)
print('effect-stats-row:', 'effect-stats-row' in html)
print('effect-section-label:', 'effect-section-label' in html)
print('effect-gen-btn:', 'effect-gen-btn' in html)
print('effect-detail-table:', 'effect-detail-table' in html)
print('renderEffectStats:', 'renderEffectStats' in html)
print('renderEffectDetails:', 'renderEffectDetails' in html)
print('Filesize:', len(html))
