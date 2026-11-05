"""Managed local and optional private cloud images."""

import io
import os
import tempfile
from pathlib import Path, PureWindowsPath
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from modules import cloud_storage

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets" / "images"
MANAGED_ROOT = ROOT / "assets"


def _cloud_enabled():
    return os.getenv("CLOUD_DEPLOYMENT") == "1"


def _managed_file(value):
    if not value or str(value).startswith(("http://", "https://")):
        return None
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    try:
        absolute = Path(os.path.abspath(path))
        absolute.relative_to(MANAGED_ROOT)
        current = absolute
        while current != ROOT:
            if current.is_symlink() or (
                current.exists()
                and getattr(current.stat(), "st_file_attributes", 0) & 0x400
            ):
                return None
            current = current.parent
        if (
            not absolute.resolve().is_relative_to(MANAGED_ROOT.resolve())
            or not absolute.is_file()
        ):
            return None
        return absolute
    except (ValueError, OSError):
        return None


def process_and_save_image(uploaded_file) -> str:
    if uploaded_file is None:
        raise ValueError("Please choose an image file.")
    path = None
    cloud_content = None
    try:
        with Image.open(uploaded_file) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((1600, 1600))
            if image.mode != "RGB":
                image = image.convert("RGB")
            if _cloud_enabled():
                content = io.BytesIO()
                image.save(content, "JPEG", quality=85, optimize=True)
                cloud_content = content.getvalue()
            else:
                ASSETS_DIR.mkdir(parents=True, exist_ok=True)
                path = ASSETS_DIR / f"{uuid4().hex}.jpg"
                image.save(path, "JPEG", quality=85, optimize=True)
                return path.relative_to(ROOT).as_posix()
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ) as exc:
        if path is not None:
            safe_remove_file(path)
        raise ValueError("The selected file is not a valid supported image.") from exc
    try:
        return cloud_storage.upload_image(f"{uuid4().hex}.jpg", cloud_content)
    except cloud_storage.CloudStorageError as exc:
        raise ValueError(str(exc)) from None


def _local_image_path(path):
    if path and "://" in str(path):
        return None
    managed = _managed_file(path)
    if managed is None and path:
        # Recover legacy absolute references following a workspace move.
        parts = PureWindowsPath(str(path)).parts
        if len(parts) >= 3 and parts[-3:-1] == ("assets", "images"):
            managed = _managed_file(Path("assets") / "images" / parts[-1])
    return str(managed) if managed else None


def normalize_image_reference(path):
    if cloud_storage.image_key(path):
        return str(path)
    return _local_image_path(path)


def _cache_path(uri):
    key = cloud_storage.image_key(uri)
    if not key:
        return None
    directory = Path(
        os.getenv(
            "IMAGE_CACHE_DIR",
            str(Path(tempfile.gettempdir()) / "lab-inventory" / "images"),
        )
    )
    try:
        directory.mkdir(parents=True, exist_ok=True)
        # Do not follow a symlink/reparse point in the cache directory or file.
        for item in (directory, *directory.parents):
            if item.is_symlink() or (
                item.exists() and getattr(item.stat(), "st_file_attributes", 0) & 0x400
            ):
                return None
        path = directory / key.rsplit("/", 1)[-1]
        if path.is_symlink() or (
            path.exists() and getattr(path.stat(), "st_file_attributes", 0) & 0x400
        ):
            return None
        return path
    except OSError:
        return None


def get_image_path(path):
    if not cloud_storage.image_key(path):
        return _local_image_path(path)
    if not _cloud_enabled():
        return None
    cache = _cache_path(path)
    if cache is None:
        return None
    try:
        if cache.is_file():
            return str(cache)
        content = cloud_storage.read_image(path)
        if not content:
            return None
        # Write only a valid image into the cache; atomically publish it.
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with tempfile.NamedTemporaryFile(dir=cache.parent, delete=False) as temp:
            temp_path = Path(temp.name)
            try:
                temp.write(content)
                temp.close()
                os.replace(temp_path, cache)
            finally:
                temp_path.unlink(missing_ok=True)
        return str(cache)
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def safe_remove_file(path) -> bool:
    if cloud_storage.image_key(path):
        if not _cloud_enabled() or not cloud_storage.delete_image(path):
            return False
        cache = _cache_path(path)
        if cache:
            try:
                cache.unlink(missing_ok=True)
            except OSError:
                pass
        return True
    managed = _managed_file(path)
    if managed is None:
        return False
    try:
        managed.unlink()
        return True
    except OSError:
        return False
