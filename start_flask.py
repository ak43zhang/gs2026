#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""启动Flask服务"""
import sys
import os

# 设置UTF-8编码
os.environ['PYTHONIOENCODING'] = 'utf-8'

sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard2.app import create_app

app = create_app()
print('Starting Flask server on http://0.0.0.0:5000')
app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
