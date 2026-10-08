import os
import sqlite3
import sys

os.chdir(r"F:\New folder (2)\careos-main test\backend")
print('CWD=', os.getcwd())
try:
    os.remove('careos.db')
except FileNotFoundError:
    pass

from app.db import init_db
import asyncio
asyncio.run(init_db())
conn = sqlite3.connect('careos.db')
print('TABLES=', conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall())
conn.close()

import pytest
rc = pytest.main(['-q', 'tests/test_auth.py'])
print('PYTEST_EXIT', rc)
sys.exit(rc)
