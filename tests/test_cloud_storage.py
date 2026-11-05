import io
import json

import pytest
from PIL import Image

from modules import cloud_storage, image_utils


def upload():
    buffer = io.BytesIO()
    Image.new("RGB", (1800, 100), "blue").save(buffer, "PNG")
    buffer.seek(0)
    return buffer


def test_cloud_upload_read_delete_and_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUD_DEPLOYMENT", "1")
    monkeypatch.setenv("IMAGE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    objects = {}
    requests = []

    class Response:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return self.body

    class Opener:
        def open(self, request, timeout):
            assert timeout == 20
            assert request.get_header("Apikey") == "sb_secret_test"
            assert request.get_header("Authorization") is None
            requests.append(request)
            method = request.get_method()
            if method == "POST":
                assert request.get_header("X-upsert") == "false"
                content_type = request.get_header("Content-type")
                assert content_type.startswith("multipart/form-data; boundary=")
                boundary = content_type.split("boundary=", 1)[1].encode()
                head, payload = request.data.split(b"\r\n\r\n", 1)
                assert b"Content-Type: image/jpeg" in head
                key = request.full_url.split("/lab-inventory-photos/", 1)[1]
                objects[key] = payload.removesuffix(b"\r\n--" + boundary + b"--\r\n")
                return Response(b"{}")
            if method == "GET":
                key = request.full_url.split("/lab-inventory-photos/", 1)[1]
                return Response(objects[key])
            assert request.full_url.endswith("/storage/v1/object/lab-inventory-photos")
            for key in json.loads(request.data)["prefixes"]:
                del objects[key]
            return Response(b"[]")

    monkeypatch.setattr(cloud_storage, "build_opener", lambda *args: Opener())
    uri = image_utils.process_and_save_image(upload())
    key = cloud_storage.image_key(uri)
    assert key in objects
    assert uri == f"supabase://{key}"
    with Image.open(io.BytesIO(objects[key])) as image:
        assert image.format == "JPEG" and image.width == 1600
    assert image_utils.normalize_image_reference(uri) == uri
    cached = image_utils.get_image_path(uri)
    assert cached and (tmp_path / "cache" / key.split("/")[-1]).read_bytes() == objects[key]
    assert "/object/authenticated/" in requests[1].full_url
    assert image_utils.safe_remove_file(uri)
    assert not objects and not (tmp_path / "cache" / key.split("/")[-1]).exists()
    assert [r.get_method() for r in requests] == ["POST", "GET", "DELETE"]


def test_cloud_namespace_and_failures(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUD_DEPLOYMENT", "1")
    monkeypatch.setenv("IMAGE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")

    def fail(*args, **kwargs):
        raise RuntimeError("secret token provider URL")

    monkeypatch.setattr(cloud_storage, "build_opener", fail)
    with pytest.raises(ValueError, match="storage is unavailable") as error:
        image_utils.process_and_save_image(upload())
    assert "secret" not in str(error.value)
    uri = "supabase://lab-inventory/images/" + "a" * 32 + ".jpg"
    assert image_utils.get_image_path(uri) is None
    assert image_utils.safe_remove_file(uri) is False
    for value in (
        "supabase://lab-inventory/images/../private.jpg",
        "supabase://other/images/" + "a" * 32 + ".jpg",
        "https://example.test/secret",
        uri + "?token=secret",
    ):
        assert image_utils.normalize_image_reference(value) is None
        assert image_utils.get_image_path(value) is None
        assert not image_utils.safe_remove_file(value)
    monkeypatch.delenv("CLOUD_DEPLOYMENT")
    assert image_utils.get_image_path(uri) is None
    assert not image_utils.safe_remove_file(uri)


def test_invalid_storage_config_never_sends_key(monkeypatch):
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setattr(cloud_storage, "build_opener", lambda *args: pytest.fail("unexpected request"))
    for url, bucket in (("http://example.supabase.co", "photos"),
                        ("https://user@example.supabase.co", "photos"),
                        ("https://example.supabase.co", "../photos")):
        monkeypatch.setenv("SUPABASE_URL", url)
        monkeypatch.setenv("SUPABASE_STORAGE_BUCKET", bucket)
        with pytest.raises(cloud_storage.CloudStorageError):
            cloud_storage.upload_image("a" * 32 + ".jpg", b"image")


def test_local_reference_normalization_and_no_cloud(tmp_path, monkeypatch):
    monkeypatch.delenv("CLOUD_DEPLOYMENT", raising=False)
    monkeypatch.setattr(image_utils, "ROOT", tmp_path)
    monkeypatch.setattr(image_utils, "MANAGED_ROOT", tmp_path / "assets")
    monkeypatch.setattr(image_utils, "ASSETS_DIR", tmp_path / "assets" / "images")
    monkeypatch.setattr(cloud_storage, "build_opener", lambda *args: pytest.fail("unexpected cloud call"))
    path = image_utils.process_and_save_image(upload())
    assert image_utils.normalize_image_reference(path) == str(tmp_path / path)
    assert image_utils.safe_remove_file(path)
