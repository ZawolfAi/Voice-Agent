import os
import tempfile
from pathlib import Path

os.environ.setdefault("APP_ENV", "test")
test_database = Path(tempfile.gettempdir()) / f"careos-pytest-{os.getpid()}.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{test_database.as_posix()}"
os.environ.setdefault("OIDC_ISSUER_URL", "https://issuer.example.com")
os.environ.setdefault("OIDC_CLIENT_ID", "careos-test-client")
os.environ.setdefault("OIDC_CLIENT_SECRET", "careos-test-secret")
os.environ.setdefault("APP_URL", "http://localhost:5173")
