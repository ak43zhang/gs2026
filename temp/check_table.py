#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))

from gs2026.dashboard.services.data_service import DataService
from sqlalchemy import text

ds = DataService()
with ds.engine.connect() as conn:
    result = conn.execute(text("SHOW TABLES LIKE 'quant_screen_hits'"))
    tables = result.fetchall()
    print('表存在:', len(tables) > 0)
    if tables:
        result = conn.execute(text('SELECT COUNT(*) FROM quant_screen_hits'))
        count = result.scalar()
        print('记录数:', count)
    else:
        print('表不存在，需要创建')
