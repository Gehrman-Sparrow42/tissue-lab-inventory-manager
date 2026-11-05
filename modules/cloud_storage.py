"""Private Blob image storage; only generated image keys are accepted."""

import re

_IMAGE_URI = re.compile(r"blob://lab-inventory/images/([0-9a-f]{32}\.jpg)\Z")


class CloudStorageError(Exception):
    """A cloud operation failed without exposing provider details."""


def image_key(uri):
    match = _IMAGE_URI.fullmatch(str(uri or ""))
    return f"lab-inventory/images/{match.group(1)}" if match else None


def upload_image(name, content):
    uri = f"blob://lab-inventory/images/{name}"
    key = image_key(uri)
    if key is None:
        raise ValueError("Invalid managed image name.")
    try:
        from vercel.blob import sync

        sync.put_blob(key, content, access="private", content_type="image/jpeg")
    except Exception:  # noqa: BLE001 - sanitize third-party provider failures
        # Provider exceptions can contain request credentials or access-bearing URLs.
        raise CloudStorageError(
            "Image storage is unavailable. Please try again."
        ) from None
    return uri


def read_image(uri):
    key = image_key(uri)
    if key is None:
        return None
    try:
        from vercel.blob import sync

        return sync.get_blob(key, access="private").body
    except Exception:  # noqa: BLE001 - sanitize third-party provider failures
        return None


def delete_image(uri):
    key = image_key(uri)
    if key is None:
        return False
    try:
        from vercel.blob import sync

        sync.delete_blob(key)
        return True
    except Exception:  # noqa: BLE001 - sanitize third-party provider failures
        return False
