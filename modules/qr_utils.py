import qrcode
import os
from dotenv import load_dotenv

load_dotenv(override=True)
BASE_URL = os.getenv("BASE_URL", "http://localhost:8501")
ASSETS_DIR = "assets/qrcodes"
os.makedirs(ASSETS_DIR, exist_ok=True)

def generate_qr_code(identifier: str, entity_type: str) -> str:
    """Generates a QR code linking to the specific domain/link for the entity."""
    url = f"{BASE_URL}/?type={entity_type}&id={identifier}"
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    safe_id = str(identifier).replace(" ", "_").replace("/", "_")
    file_path = os.path.join(ASSETS_DIR, f"{entity_type}_{safe_id}.png")
    img.save(file_path)
    return file_path
