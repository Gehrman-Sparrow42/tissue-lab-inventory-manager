import base64
import importlib.util
from pathlib import Path

import pytest

from modules import ui


def start_module():
    path = Path(__file__).resolve().parents[1] / "deployment" / "start.py"
    spec = importlib.util.spec_from_file_location("cloud_entrypoint", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hosted_start_rejects_ephemeral_database(monkeypatch):
    monkeypatch.setenv("DB_PATH", "data/inventory.db")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        start_module().configure_environment()


def test_hosted_start_requires_secrets_and_sets_cache(tmp_path, monkeypatch):
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://example:example@db.invalid/inventory"
    )
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Supabase Storage"):
        start_module().configure_environment()
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    with pytest.raises(RuntimeError, match="Supabase Storage"):
        start_module().configure_environment()
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin")
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        start_module().configure_environment()
    monkeypatch.setenv("ADMIN_PASSWORD", "private-test-password")
    monkeypatch.setenv("STREAMLIT_SERVER_COOKIE_SECRET", "private-test-cookie-secret")
    monkeypatch.setenv("BASE_URL", "https://inventory.example.test")
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("PORT", "8080")
    monkeypatch.delenv("QR_CACHE_DIR", raising=False)
    monkeypatch.delenv("IMAGE_CACHE_DIR", raising=False)
    assert start_module().configure_environment() == 8080
    import os

    assert os.environ["DB_PATH"].startswith("postgresql://")
    assert os.environ["QR_CACHE_DIR"] == str(tmp_path / "cache" / "qrcodes")


def test_cloud_images_travel_inline(monkeypatch):
    monkeypatch.setenv("CLOUD_DEPLOYMENT", "1")
    images = []
    monkeypatch.setattr(ui.st, "image", lambda image, **kwargs: images.append(image))
    payload = b"\x89PNG\r\n\x1a\nmock-image"
    ui.show_image(payload, width=100)
    assert images[0].startswith("data:image/png;base64,")
    assert base64.b64decode(images[0].split(",", 1)[1]) == payload


def test_cloud_download_does_not_use_instance_media(monkeypatch):
    monkeypatch.setenv("CLOUD_DEPLOYMENT", "1")
    output = []
    monkeypatch.setattr(ui.st, "markdown", lambda html, **kwargs: output.append(html))
    ui.download_file("Download", b"a,b\n1,2", 'inventory".csv', "text/csv")
    assert 'download="inventory&quot;.csv"' in output[0]
    assert "data:text/csv;base64,YSxiCjEsMg==" in output[0]
