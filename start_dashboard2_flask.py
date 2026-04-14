#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""启动Dashboard2 Flask服务 (端口8080)"""
import sys
import os

# 设置UTF-8编码
os.environ['PYTHONIOENCODING'] = 'utf-8'

sys.path.insert(0, r'F:\pyworkspace2026\gs2026\src')

from gs2026.dashboard2.app import create_app

app = create_app()
print('Starting Dashboard2 Flask server on http://0.0.0.0:8080')
app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)
