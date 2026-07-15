import urllib.parse
import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)
BASE_URL = os.getenv("BASE_URL", "http://localhost:8501")

def generate_qr_code(identifier: str, entity_type: str) -> str:
    """Generates a dynamic QR code API link for the entity with a white border (quiet zone)."""
    target_url = f"{BASE_URL}/?type={entity_type}&id={identifier}"
    encoded_url = urllib.parse.quote(target_url)
    return f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={encoded_url}&margin=15"

def get_qr_bytes(path_or_url: str) -> bytes:
    """Fetches QR code image bytes from URL or local path on demand."""
    if not path_or_url:
        return b""
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        try:
            return requests.get(path_or_url, timeout=5).content
        except Exception:
            return b""
    else:
        try:
            with open(path_or_url, "rb") as f:
                return f.read()
        except Exception:
            return b""
