"""Managed image and QR files."""

import os
from pathlib import Path, PureWindowsPath
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets" / "images"
MANAGED_ROOT = ROOT / "assets"


def _managed_file(value):
    if not value or str(value).startswith(("http://", "https://")):
        return None
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    try:
        # Reject links even when they resolve back inside the asset directory.
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
    try:
        with Image.open(uploaded_file) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((1600, 1600))
            if image.mode != "RGB":
                image = image.convert("RGB")
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


def get_image_path(path):
    managed = _managed_file(path)
    if managed is None and path:
        # Recover images stored with an absolute path before a workspace move.
        # Resolve only the managed image suffix and retain all link checks.
        parts = PureWindowsPath(str(path)).parts
        if len(parts) >= 3 and parts[-3:-1] == ("assets", "images"):
            managed = _managed_file(Path("assets") / "images" / parts[-1])
    return str(managed) if managed else None


def safe_remove_file(path) -> bool:
    managed = _managed_file(path)
    if managed is None:
        return False
    try:
        managed.unlink()
        return True
    except OSError:
        return False
