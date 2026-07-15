import os
from PIL import Image
import uuid

ASSETS_DIR = "assets/images"
os.makedirs(ASSETS_DIR, exist_ok=True)

def process_and_save_image(uploaded_file) -> str:
    """Resizes image to max 800x800 and saves it. Returns the file path."""
    if not uploaded_file:
        return ""
        
    img = Image.open(uploaded_file)
    
    if img.mode != 'RGB':
        img = img.convert('RGB')
        
    img.thumbnail((800, 800), Image.Resampling.LANCZOS)
    
    filename = f"{uuid.uuid4().hex}.jpg"
    file_path = os.path.join(ASSETS_DIR, filename)
    
    img.save(file_path, format="JPEG", quality=85)
    return file_path

def safe_remove_file(file_path: str):
    """Safely deletes a file from disk if it exists."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass
