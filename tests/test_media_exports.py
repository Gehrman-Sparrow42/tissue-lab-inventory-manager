import csv
import io
from urllib.parse import parse_qs, urlsplit

import pytest
from PIL import Image
from sqlmodel import Session, SQLModel, create_engine

from modules import image_utils, qr_utils
from modules.exports import inventory_csv, printable_labels
from modules.models import Rack, Species, Variety, Vessel


def test_qr_encoding_cache_and_legacy_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(qr_utils, "QR_DIR", tmp_path)
    monkeypatch.setenv("BASE_URL", "http://example.test:8501/sub")
    captured = []
    real_png = qr_utils._png
    monkeypatch.setattr(
        qr_utils, "_png", lambda text: captured.append(text) or real_png(text)
    )
    path = qr_utils.generate_qr_code("a &/#%", "rack")
    assert parse_qs(urlsplit(captured[0]).query) == {"type": ["rack"], "id": ["a &/#%"]}
    assert qr_utils.get_qr_bytes(path).startswith(b"\x89PNG")
    assert qr_utils.generate_qr_code("a &/#%", "rack") == path
    monkeypatch.setenv("BASE_URL", "https://different.test")
    assert qr_utils.generate_qr_code("a &/#%", "rack") != path
    assert qr_utils.get_qr_bytes(
        "https://api.qrserver.com/v1/create-qr-code/?data=hello%26world"
    ).startswith(b"\x89PNG")
    assert captured[-1] == "hello&world"
    assert qr_utils.get_qr_bytes("https://example.com/evil") == b""
    monkeypatch.setenv("BASE_URL", "https://user:password@example.test")
    with pytest.raises(ValueError):
        qr_utils.generate_qr_code("x", "rack")
    monkeypatch.setenv("BASE_URL", "http://localhost:8501")
    with pytest.raises(ValueError, match="too long"):
        qr_utils.generate_qr_code("x" * 10000, "rack")


def test_managed_image_and_deletion(tmp_path, monkeypatch):
    monkeypatch.setattr(image_utils, "ROOT", tmp_path)
    monkeypatch.setattr(image_utils, "MANAGED_ROOT", tmp_path / "assets")
    monkeypatch.setattr(image_utils, "ASSETS_DIR", tmp_path / "assets" / "images")
    upload = io.BytesIO()
    Image.new("RGB", (2000, 100), "red").save(upload, "PNG")
    upload.seek(0)
    path = image_utils.process_and_save_image(upload)
    resolved = tmp_path / path
    with Image.open(resolved) as result:
        assert result.format == "JPEG"
        assert result.width == 1600
    assert image_utils.get_image_path(path) == str(resolved)
    outside = tmp_path / "outside.txt"
    outside.write_text("keep")
    assert not image_utils.safe_remove_file(outside)
    assert outside.exists()
    assert image_utils.safe_remove_file(path)
    assert not resolved.exists()
    with pytest.raises(ValueError):
        image_utils.process_and_save_image(io.BytesIO(b"not an image"))


def test_exports_include_hierarchy_escape_and_embed(tmp_path, monkeypatch):
    monkeypatch.setattr(qr_utils, "QR_DIR", tmp_path)
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        species = Species(name="=formula")
        session.add(species)
        session.flush()
        variety = Variety(name="<variety>", species_id=species.id)
        session.add(variety)
        session.flush()
        rack = Rack(
            rack_identifier="R&1", variety_id=variety.id, metadata_json='{"pH": 5.8}'
        )
        session.add(rack)
        session.flush()
        session.add(Vessel(vessel_identifier="V#1", rack_id=rack.id))
        session.commit()
        rows = list(
            csv.DictReader(io.StringIO(inventory_csv(session).decode("utf-8-sig")))
        )
        assert {r["level"] for r in rows} == {"species", "variety", "rack", "vessel"}
        assert rows[0]["species"] == "'=formula"
        assert any('"pH": 5.8' in r.get("metadata_json", "") for r in rows)
        page = printable_labels(session).decode()
        assert page.count("data:image/png;base64,") == 4
        assert "&lt;variety&gt;" in page and "R&amp;1" in page and "V#1" in page


def test_image_paths_survive_workspace_relocation(tmp_path, monkeypatch):
    import shutil

    original_root = tmp_path / "original"
    moved_root = tmp_path / "moved"
    monkeypatch.setattr(image_utils, "ROOT", original_root)
    monkeypatch.setattr(image_utils, "MANAGED_ROOT", original_root / "assets")
    monkeypatch.setattr(image_utils, "ASSETS_DIR", original_root / "assets" / "images")
    upload = io.BytesIO()
    Image.new("RGB", (20, 20), "green").save(upload, "PNG")
    upload.seek(0)
    relative = image_utils.process_and_save_image(upload)
    assert relative.startswith("assets/images/")
    old_absolute = original_root / relative
    target = moved_root / relative
    target.parent.mkdir(parents=True)
    shutil.copyfile(old_absolute, target)
    monkeypatch.setattr(image_utils, "ROOT", moved_root)
    monkeypatch.setattr(image_utils, "MANAGED_ROOT", moved_root / "assets")
    assert image_utils.get_image_path(relative) == str(target)
    assert image_utils.get_image_path(str(old_absolute)) == str(target)
    assert not image_utils.safe_remove_file(str(old_absolute))
    assert old_absolute.exists() and target.exists()


def test_qr_paths_are_project_relative(tmp_path, monkeypatch):
    monkeypatch.setattr(qr_utils, "ROOT", tmp_path)
    monkeypatch.setattr(qr_utils, "QR_DIR", tmp_path / "assets" / "qrcodes")
    monkeypatch.setenv("BASE_URL", "http://localhost:8501")
    path = qr_utils.generate_qr_code("R1", "rack")
    assert path.startswith("assets/qrcodes/")
    assert qr_utils.get_qr_bytes(path).startswith(b"\x89PNG")
