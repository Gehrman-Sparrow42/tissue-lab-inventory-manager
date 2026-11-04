"""Offline QR generation and compatibility with previously stored QR URLs."""

import hashlib
import io
import os
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import qrcode
from dotenv import load_dotenv
from qrcode.exceptions import DataOverflowError

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
QR_DIR = ROOT / "assets" / "qrcodes"


def _target_url(identifier: str, entity_type: str) -> str:
    base = os.getenv("BASE_URL", "http://localhost:8501").strip()
    parts = urlsplit(base)
    try:
        valid = (
            parts.scheme in ("http", "https")
            and parts.hostname
            and not any(c.isspace() for c in parts.netloc)
            and parts.port != 0
        )
    except ValueError:
        valid = False
    if (
        not valid
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
    ):
        raise ValueError(
            "BASE_URL must be an HTTP(S) URL with a host and no credentials, query, or fragment."
        )
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path.rstrip("/") + "/",
            urlencode({"type": entity_type, "id": identifier}),
            "",
        )
    )


def _png(data: str) -> bytes:
    buffer = io.BytesIO()
    try:
        qrcode.make(data).save(buffer, format="PNG")
    except (DataOverflowError, ValueError) as exc:
        raise ValueError(
            "The label URL is too long for a QR code. Shorten its identifier or BASE_URL."
        ) from exc
    return buffer.getvalue()


def generate_qr_code(identifier: str, entity_type: str) -> str:
    target = _target_url(str(identifier), str(entity_type))
    QR_DIR.mkdir(parents=True, exist_ok=True)
    path = QR_DIR / (hashlib.sha256(target.encode("utf-8")).hexdigest() + ".png")
    if not path.is_file():
        # Publish a complete PNG atomically when multiple sessions request it.
        temporary = path.with_suffix(f".{uuid4().hex}.tmp")
        temporary.write_bytes(_png(target))
        os.replace(temporary, path)
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def get_qr_bytes(path_or_url: str) -> bytes:
    if not path_or_url:
        return b""
    parts = urlsplit(str(path_or_url))
    if parts.scheme in ("http", "https"):
        if parts.hostname != "api.qrserver.com":
            return b""
        data = parse_qs(parts.query).get("data", [])
        return _png(data[0]) if data else b""
    try:
        path = Path(path_or_url)
        if not path.is_absolute():
            path = ROOT / path
        return path.read_bytes()
    except (OSError, ValueError):
        return b""
