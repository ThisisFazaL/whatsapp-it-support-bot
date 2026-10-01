import os
import sys
import asyncio
import pytest

# Point tests to local SQLite database so test suites run in ~3 seconds instead of 10+ minutes over cloud WAN
TEST_DB_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tests_local.db"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_FILE}"
os.environ["APP_ENV"] = "testing"

@pytest.fixture(scope="session", autouse=True)
def prepare_and_cleanup_test_database():
    from app.database import init_db_models
    try:
        asyncio.run(init_db_models())
    except Exception as e:
        print(f"Test DB init note: {e}")
    yield
    # Teardown: remove local test database file
    for suffix in ["", "-shm", "-wal"]:
        fpath = f"{TEST_DB_FILE}{suffix}"
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass
