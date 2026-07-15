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
s1 = Species(name="Arabidopsis thaliana", description="Model organism for plant biology.", metadata_schema='[{"name": "pH", "type": "number", "default": 5.8}, {"name": "Light Intensity", "type": "number", "default": 2500}, {"name": "Agar Concentration %", "type": "number", "default": 0.8}]')
s2 = Species(name="Oryza sativa", description="Asian rice, major cereal crop.", metadata_schema='[{"name": "pH", "type": "number", "default": 5.5}, {"name": "Light Intensity", "type": "number", "default": 3000}, {"name": "Nitrogen Level", "type": "text", "default": "High"}]')
s3 = Species(name="Phalaenopsis", description="Moth orchids, popular ornamental plants.", metadata_schema='[{"name": "pH", "type": "number", "default": 5.2}, {"name": "Light Intensity", "type": "number", "default": 1500}, {"name": "Hormones", "type": "text", "default": "BAP/NAA"}]')

session.add_all([s1, s2, s3])
session.commit()
session.refresh(s1); session.refresh(s2); session.refresh(s3)

s1.qr_code_path = generate_qr_code(str(s1.id), "species")
s2.qr_code_path = generate_qr_code(str(s2.id), "species")
s3.qr_code_path = generate_qr_code(str(s3.id), "species")
session.add_all([s1, s2, s3])
session.commit()

# 2. Add Varieties
v1 = Variety(name="Col-0", species_id=s1.id, description="Columbia-0 ecotype.")
v2 = Variety(name="Ler-0", species_id=s1.id, description="Landsberg erecta ecotype.")
v3 = Variety(name="Nipponbare", species_id=s2.id, description="Japonica rice variety.")
v4 = Variety(name="Amabilis", species_id=s3.id, description="White moth orchid.")

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

r1 = Rack(rack_identifier="RACK-ARAB-001", variety_id=v1.id, qr_code_path=generate_qr_code("RACK-ARAB-001", "rack"), image_url=process_img(img1), metadata_json=json.dumps({"pH": 5.8, "Light Intensity": 2500, "Agar Concentration %": 0.8}))
r2 = Rack(rack_identifier="RACK-ARAB-002", variety_id=v2.id, qr_code_path=generate_qr_code("RACK-ARAB-002", "rack"), image_url=process_img(img1), metadata_json=json.dumps({"pH": 5.8, "Light Intensity": 2500, "Agar Concentration %": 0.8}))
r3 = Rack(rack_identifier="RACK-RICE-001", variety_id=v3.id, qr_code_path=generate_qr_code("RACK-RICE-001", "rack"), image_url=process_img(img2), metadata_json=json.dumps({"pH": 5.5, "Light Intensity": 3000, "Nitrogen Level": "High"}))
r4 = Rack(rack_identifier="RACK-ORCH-001", variety_id=v4.id, qr_code_path=generate_qr_code("RACK-ORCH-001", "rack"), image_url=process_img(img3), metadata_json=json.dumps({"pH": 5.2, "Light Intensity": 1500, "Hormones": "BAP/NAA"}))

session.add_all([r1, r2, r3, r4])
session.commit()
print("Populated database successfully!")
