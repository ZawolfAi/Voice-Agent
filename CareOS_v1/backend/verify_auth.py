import os
import sys

root = r"F:\New folder (2)\careos-main test\backend"
os.chdir(root)
result_path = os.path.join(root, "verification_result.txt")

try:
    os.remove("careos.db")
except FileNotFoundError:
    pass

print("START_VERIFY", flush=True)

import pytest
rc = pytest.main(["-q", "tests/test_auth.py", "--disable-warnings"])

with open(result_path, "w", encoding="utf-8") as f:
    f.write(f"PYTEST_EXIT={rc}\n")

print(f"PYTEST_EXIT={rc}", flush=True)
sys.exit(rc)
