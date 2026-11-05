"""Private Supabase image storage with strictly scoped object references."""

import json
import os
import re
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

_IMAGE_URI = re.compile(r"supabase://lab-inventory/images/([0-9a-f]{32}\.jpg)\Z")
_BUCKET = re.compile(r"[a-z0-9][a-z0-9._-]{0,99}\Z")
_TIMEOUT = 20


class CloudStorageError(Exception):
    """A cloud operation failed without exposing provider details."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def image_key(uri):
    match = _IMAGE_URI.fullmatch(str(uri or ""))
    return f"lab-inventory/images/{match.group(1)}" if match else None


def _request(method, key, content=None):
    base = os.getenv("SUPABASE_URL", "").rstrip("/")
    secret = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    bucket = os.getenv("SUPABASE_STORAGE_BUCKET", "lab-inventory-photos")
    parsed = urlsplit(base)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or not secret
        or not _BUCKET.fullmatch(bucket)
    ):
        raise CloudStorageError("Image storage is unavailable. Please try again.")
    headers = {"apikey": secret}
    if not secret.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {secret}"
    if method == "POST":
        url = f"{base}/storage/v1/object/{bucket}/{key}"
        boundary = f"inventory-{uuid4().hex}"
        content = (
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                'filename="image.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'
            ).encode("ascii")
            + content
            + f"\r\n--{boundary}--\r\n".encode("ascii")
        )
        headers.update(
            {
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "x-upsert": "false",
            }
        )
    elif method == "GET":
        url = f"{base}/storage/v1/object/authenticated/{bucket}/{key}"
    else:
        url = f"{base}/storage/v1/object/{bucket}"
        headers["Content-Type"] = "application/json"
        content = json.dumps({"prefixes": [key]}).encode("utf-8")
    request = Request(url, data=content, headers=headers, method=method)
    with build_opener(_NoRedirect()).open(request, timeout=_TIMEOUT) as response:
        return response.read()


def upload_image(name, content):
    uri = f"supabase://lab-inventory/images/{name}"
    key = image_key(uri)
    if key is None:
        raise ValueError("Invalid managed image name.")
    try:
        _request("POST", key, content)
    except Exception:  # noqa: BLE001 - provider errors may contain credentials
        raise CloudStorageError(
            "Image storage is unavailable. Please try again."
        ) from None
    return uri


def read_image(uri):
    key = image_key(uri)
    if key is None:
        return None
    try:
        return _request("GET", key)
    except Exception:  # noqa: BLE001 - do not expose provider errors
        return None


def delete_image(uri):
    key = image_key(uri)
    if key is None:
        return False
    try:
        _request("DELETE", key)
        return True
    except Exception:  # noqa: BLE001 - do not expose provider errors
        return False
