import os
import sqlite3
import sys

root = r"F:\New folder (2)\careos-main test\backend"
os.chdir(root)
report_path = os.path.join(root, 'verification_report.txt')

try:
    os.remove('careos.db')
except FileNotFoundError:
    pass

try:
    import asyncio
    from app.db import init_db, engine
    asyncio.run(init_db())
    conn = sqlite3.connect('careos.db')
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    conn.close()
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('DB_TABLES=' + repr(tables) + '\n')
    import pytest
    rc = pytest.main(['-q', 'tests/test_auth.py'])
    with open(report_path, 'a', encoding='utf-8') as f:
        f.write('PYTEST_EXIT=' + str(rc) + '\n')
    sys.exit(rc)
finally:
    try:
        import asyncio
        from app.db import engine
        asyncio.run(engine.dispose())
    except Exception:
        pass
