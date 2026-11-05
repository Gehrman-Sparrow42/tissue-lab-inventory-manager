import io
from types import SimpleNamespace

import pytest
from PIL import Image
from vercel.blob import sync

from modules import cloud_storage, image_utils


def upload():
    buffer = io.BytesIO()
    Image.new("RGB", (1800, 100), "blue").save(buffer, "PNG")
    buffer.seek(0)
    return buffer


def test_cloud_upload_read_delete_and_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUD_DEPLOYMENT", "1")
    monkeypatch.setenv("IMAGE_CACHE_DIR", str(tmp_path / "cache"))
    objects = {}

    def put(key, body, **kwargs):
        assert kwargs == {"access": "private", "content_type": "image/jpeg"}
        objects[key] = body

    def get(key, **kwargs):
        assert kwargs == {"access": "private"}
        return SimpleNamespace(body=objects[key])

    def delete(key):
        del objects[key]

    monkeypatch.setattr(sync, "put_blob", put)
    monkeypatch.setattr(sync, "get_blob", get)
    monkeypatch.setattr(sync, "delete_blob", delete)
    uri = image_utils.process_and_save_image(upload())
    key = cloud_storage.image_key(uri)
    assert key in objects
    with Image.open(io.BytesIO(objects[key])) as image:
        assert image.format == "JPEG" and image.width == 1600
    assert image_utils.normalize_image_reference(uri) == uri
    cached = image_utils.get_image_path(uri)
    assert (
        cached
        and (tmp_path / "cache" / key.split("/")[-1]).read_bytes() == objects[key]
    )
    assert image_utils.safe_remove_file(uri)
    assert not objects and not (tmp_path / "cache" / key.split("/")[-1]).exists()


def test_cloud_namespace_and_failures(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUD_DEPLOYMENT", "1")
    monkeypatch.setenv("IMAGE_CACHE_DIR", str(tmp_path / "cache"))

    def fail(*args, **kwargs):
        raise RuntimeError("secret token provider URL")

    monkeypatch.setattr(sync, "put_blob", fail)
    monkeypatch.setattr(sync, "get_blob", fail)
    monkeypatch.setattr(sync, "delete_blob", fail)
    with pytest.raises(ValueError, match="storage is unavailable") as error:
        image_utils.process_and_save_image(upload())
    assert "secret" not in str(error.value)
    uri = "blob://lab-inventory/images/" + "a" * 32 + ".jpg"
    assert image_utils.get_image_path(uri) is None
    assert image_utils.safe_remove_file(uri) is False
    for value in (
        "blob://lab-inventory/images/../private.jpg",
        "blob://other/images/" + "a" * 32 + ".jpg",
        "https://example.test/secret",
        uri + "?token=secret",
    ):
        assert image_utils.normalize_image_reference(value) is None
        assert image_utils.get_image_path(value) is None
        assert not image_utils.safe_remove_file(value)
    monkeypatch.delenv("CLOUD_DEPLOYMENT")
    assert image_utils.get_image_path(uri) is None
    assert not image_utils.safe_remove_file(uri)


def test_local_reference_normalization_and_no_cloud(tmp_path, monkeypatch):
    monkeypatch.delenv("CLOUD_DEPLOYMENT", raising=False)
    monkeypatch.setattr(image_utils, "ROOT", tmp_path)
    monkeypatch.setattr(image_utils, "MANAGED_ROOT", tmp_path / "assets")
    monkeypatch.setattr(image_utils, "ASSETS_DIR", tmp_path / "assets" / "images")
    monkeypatch.setattr(
        sync, "put_blob", lambda *args, **kwargs: pytest.fail("unexpected cloud call")
    )
    path = image_utils.process_and_save_image(upload())
    assert image_utils.normalize_image_reference(path) == str(tmp_path / path)
    assert image_utils.safe_remove_file(path)
