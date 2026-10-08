import asyncio
import os
import sqlite3
import sys

root = r"F:\New folder (2)\careos-main test\backend"
os.chdir(root)

for path in ["careos.db", "verification_result.txt"]:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass

from app.db import init_db, engine

async def main():
    await init_db()
    conn = sqlite3.connect("careos.db")
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    conn.close()
    print("TABLES=" + repr(tables))
    await engine.dispose()

asyncio.run(main())

import pytest
rc = pytest.main(["-q", "tests/test_auth.py", "--disable-warnings"])
with open("verification_result.txt", "w", encoding="utf-8") as f:
    f.write(f"PYTEST_EXIT={rc}\n")
print(f"PYTEST_EXIT={rc}")
sys.exit(rc)
