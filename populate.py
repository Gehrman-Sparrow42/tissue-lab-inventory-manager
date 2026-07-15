import sys
import os
import json
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.database import get_session, create_db_and_tables
from modules.models import Species, Variety, Rack
from modules.qr_utils import generate_qr_code
from modules.image_utils import process_and_save_image
from sqlmodel import select

create_db_and_tables()

session = get_session()

# Check if already populated
existing = session.exec(select(Species)).first()
if existing:
    print("Database already populated. Exiting.")
    sys.exit(0)

# 1. Add Species
s1 = Species(name="Trial 1", description="First laboratory testing category.", metadata_schema='[{"name": "pH", "type": "number", "default": 5.8}, {"name": "Light Intensity", "type": "number", "default": 2500}, {"name": "Agar Concentration %", "type": "number", "default": 0.8}]')
s2 = Species(name="Trial 2", description="Second laboratory testing category.", metadata_schema='[{"name": "pH", "type": "number", "default": 5.5}, {"name": "Light Intensity", "type": "number", "default": 3000}, {"name": "Nitrogen Level", "type": "text", "default": "High"}]')
s3 = Species(name="Trial 3", description="Third laboratory testing category.", metadata_schema='[{"name": "pH", "type": "number", "default": 5.2}, {"name": "Light Intensity", "type": "number", "default": 1500}, {"name": "Hormones", "type": "text", "default": "Standard"}]')

session.add_all([s1, s2, s3])
session.commit()
session.refresh(s1); session.refresh(s2); session.refresh(s3)

s1.qr_code_path = generate_qr_code(str(s1.id), "species")
s2.qr_code_path = generate_qr_code(str(s2.id), "species")
s3.qr_code_path = generate_qr_code(str(s3.id), "species")
session.add_all([s1, s2, s3])
session.commit()

# 2. Add Varieties
v1 = Variety(name="Variety 1", species_id=s1.id, description="First variant strain.")
v2 = Variety(name="Variety 2", species_id=s1.id, description="Second variant strain.")
v3 = Variety(name="Variety 3", species_id=s2.id, description="Third variant strain.")
v4 = Variety(name="Variety 4", species_id=s3.id, description="Fourth variant strain.")

session.add_all([v1, v2, v3, v4])
session.commit()
session.refresh(v1); session.refresh(v2); session.refresh(v3); session.refresh(v4)

v1.qr_code_path = generate_qr_code(str(v1.id), "variety")
v2.qr_code_path = generate_qr_code(str(v2.id), "variety")
v3.qr_code_path = generate_qr_code(str(v3.id), "variety")
v4.qr_code_path = generate_qr_code(str(v4.id), "variety")
session.add_all([v1, v2, v3, v4])
session.commit()

# 3. Add Racks
def process_img(path):
    if not os.path.exists(path): return None
    return process_and_save_image(path)

img1 = r"C:\Users\Administrator\.gemini\antigravity\brain\801438ae-d695-472e-9a33-d3156e7a9f52\arabidopsis_rack_1784052079471.png"
img2 = r"C:\Users\Administrator\.gemini\antigravity\brain\801438ae-d695-472e-9a33-d3156e7a9f52\rice_rack_1784052087641.png"
img3 = r"C:\Users\Administrator\.gemini\antigravity\brain\801438ae-d695-472e-9a33-d3156e7a9f52\orchid_rack_1784052096118.png"

r1 = Rack(rack_identifier="RACK-001", variety_id=v1.id, name="Rack 1", description="First container tray.", qr_code_path=generate_qr_code("RACK-001", "rack"), image_url=process_img(img1), metadata_json=json.dumps({"pH": 5.8, "Light Intensity": 2500, "Agar Concentration %": 0.8}))
r2 = Rack(rack_identifier="RACK-002", variety_id=v2.id, name="Rack 2", description="Second container tray.", qr_code_path=generate_qr_code("RACK-002", "rack"), image_url=process_img(img1), metadata_json=json.dumps({"pH": 5.8, "Light Intensity": 2500, "Agar Concentration %": 0.8}))
r3 = Rack(rack_identifier="RACK-003", variety_id=v3.id, name="Rack 3", description="Third container tray.", qr_code_path=generate_qr_code("RACK-003", "rack"), image_url=process_img(img2), metadata_json=json.dumps({"pH": 5.5, "Light Intensity": 3000, "Nitrogen Level": "High"}))
r4 = Rack(rack_identifier="RACK-004", variety_id=v4.id, name="Rack 4", description="Fourth container tray.", qr_code_path=generate_qr_code("RACK-004", "rack"), image_url=process_img(img3), metadata_json=json.dumps({"pH": 5.2, "Light Intensity": 1500, "Hormones": "Standard"}))

session.add_all([r1, r2, r3, r4])
session.commit()
print("Populated database successfully!")
