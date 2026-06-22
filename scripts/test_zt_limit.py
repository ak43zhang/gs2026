import sys
sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')
from gs2026.monitor.module.zt_limit import get_zt_limit, is_zt

print('Module import OK')
print('300001 limit:', get_zt_limit('300001'))
print('688001 limit:', get_zt_limit('688001'))
print('ST limit:', get_zt_limit('000001', '*ST测试'))
print('920001 limit:', get_zt_limit('920001'))
print('is_zt(19.5, 300001):', is_zt(19.5, '300001'))
print('is_zt(9.5, 000001):', is_zt(9.5, '000001'))
