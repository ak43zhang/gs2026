#!/usr/bin/env python
"""检查 MySQL 端口"""

import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
result = sock.connect_ex(('192.168.0.101', 3306))
if result == 0:
    print('Port 3306: OPEN')
else:
    print(f'Port 3306: CLOSED (code {result})')
sock.close()
