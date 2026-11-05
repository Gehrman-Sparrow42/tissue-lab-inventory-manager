import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("cloud,expected_pool", [("1", "NullPool"), ("0", "QueuePool")])
def test_hosted_database_does_not_hold_idle_connections(cloud, expected_pool):
    root = Path(__file__).resolve().parents[1]
    env = dict(
        os.environ,
        DB_PATH="postgresql://inventory:test@db.invalid/postgres",
        CLOUD_DEPLOYMENT=cloud,
        PYTHONPATH=str(root),
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json; from modules.database import engine; print(json.dumps({'pool':type(engine.pool).__name__, 'driver':engine.dialect.driver}))",
        ],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(result.stdout) == {"pool": expected_pool, "driver": "psycopg2"}
