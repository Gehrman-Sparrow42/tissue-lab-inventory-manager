"""Launch the hosted inventory with durable storage and consistent session cookies."""

import os
import sys
from pathlib import Path


def configure_environment():
    database = os.getenv("DB_PATH") or os.getenv("DATABASE_URL")
    if not database or not database.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("Hosted inventory requires a PostgreSQL DATABASE_URL.")
    if not os.getenv("BLOB_READ_WRITE_TOKEN"):
        raise RuntimeError("Hosted inventory requires a private Vercel Blob store.")
    password = os.getenv("ADMIN_PASSWORD", "")
    if password.strip().lower() in {
        "",
        "admin",
        "change_this_admin_password_in_production",
    }:
        raise RuntimeError("Set a private ADMIN_PASSWORD before deployment.")
    if not os.getenv("STREAMLIT_SERVER_COOKIE_SECRET"):
        raise RuntimeError(
            "Set a persistent STREAMLIT_SERVER_COOKIE_SECRET before deployment."
        )
    base_url = os.getenv("BASE_URL")
    if not base_url:
        host = os.getenv("VERCEL_PROJECT_PRODUCTION_URL") or os.getenv("VERCEL_URL")
        if not host:
            raise RuntimeError(
                "Set BASE_URL to the hosted application's HTTPS address."
            )
        os.environ["BASE_URL"] = "https://" + host
    cache = Path(os.getenv("CACHE_DIR", "/tmp/lab-inventory"))
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["DB_PATH"] = database
    os.environ.setdefault("QR_CACHE_DIR", str(cache / "qrcodes"))
    os.environ.setdefault("IMAGE_CACHE_DIR", str(cache / "images"))
    port = int(os.getenv("PORT", "80"))
    if not 0 < port < 65536:
        raise ValueError("PORT must be between 1 and 65535.")
    return port


def main():
    port = configure_environment()
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "main.py",
            "--server.address=0.0.0.0",
            f"--server.port={port}",
            "--server.headless=true",
            "--server.fileWatcherType=none",
        ],
    )


if __name__ == "__main__":
    main()
