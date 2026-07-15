import streamlit as st
from sqlmodel import select
from modules.database import get_session, log_audit
from modules.models import Species, Variety, Rack
from modules.auth import is_admin, render_auth_ui
from modules.qr_utils import generate_qr_code
from modules.image_utils import process_and_save_image
import json
import uuid

st.set_page_config(page_title="Racks & Assets", page_icon="🧪", layout="wide")
render_auth_ui()

st.title("🧪 Racks & Assets Management")

session = get_session()

# Handling interconnected filtering
filter_v_id = st.session_state.get("filter_variety_id", None)
if filter_v_id:
    v_obj = session.get(Variety, filter_v_id)
    if v_obj:
        st.success(f"📌 Currently viewing racks for Variety: **{v_obj.name}**")
        if st.button("❌ Clear Filter to Show All Racks"):
            st.session_state.filter_variety_id = None
            st.rerun()
        st.write("---")

search_query = st.text_input("🔍 Global Search (Rack ID, Metadata)", "")

varieties_list = session.exec(select(Variety)).all()

if is_admin() and varieties_list:
    with st.expander("➕ Add New Rack", expanded=False):
        # Pre-select variety if filtering
        default_index = 0
        if filter_v_id:
            for idx, var in enumerate(varieties_list):
                if var.id == filter_v_id:
                    default_index = idx
                    break
                    
        r_variety = st.selectbox("Select Variety for New Rack", [v.id for v in varieties_list], index=default_index, format_func=lambda x: next((v.name for v in varieties_list if v.id == x), str(x)))
        
        if r_variety:
            selected_v = session.get(Variety, r_variety)
            selected_s = session.get(Species, selected_v.species_id)
            
            schema = []
            try:
                schema = json.loads(selected_s.metadata_schema)
            except:
                st.warning("Invalid metadata schema in Species configuration.")
                
            with st.form("add_rack_form"):
                r_id = st.text_input("Rack Identifier (Leave blank to auto-generate)")
                
                st.write(f"**Metadata Configuration for {selected_s.name}**")
                meta_values = {}
                cols = st.columns(2)
                for i, field in enumerate(schema):
                    fname = field.get("name", f"Field {i}")
                    ftype = field.get("type", "text")
                    fdef = field.get("default", "")
                    
                    with cols[i % 2]:
                        if ftype == "number":
                            try:
                                def_val = float(fdef) if fdef else 0.0
                            except:
                                def_val = 0.0
                            meta_values[fname] = st.number_input(fname, value=def_val)
                        else:
                            meta_values[fname] = st.text_input(fname, value=str(fdef))
                
                st.write("---")
                r_image = st.file_uploader("Upload Rack Image", type=['jpg', 'jpeg', 'png'])
                
                submitted = st.form_submit_button("Create Rack")
                if submitted:
                    if not r_id.strip():
                        r_id = f"RACK-{uuid.uuid4().hex[:8].upper()}"
                    
                    existing = session.exec(select(Rack).where(Rack.rack_identifier == r_id)).first()
                    if existing:
                        st.error("Rack ID already exists.")
                    else:
                        img_path = process_and_save_image(r_image) if r_image else None
                        qr_path = generate_qr_code(r_id, "rack")
                        
                        new_rack = Rack(
                            rack_identifier=r_id,
                            variety_id=r_variety,
                            qr_code_path=qr_path,
                            image_url=img_path,
                            metadata_json=json.dumps(meta_values)
                        )
                        session.add(new_rack)
                        session.commit()
                        log_audit(session, "CREATE", "Rack", new_rack.id, r_id)
                        st.success(f"Rack {r_id} created successfully!")
                        st.rerun()

st.subheader("Rack Inventory")

query = select(Rack)
if filter_v_id:
    query = query.where(Rack.variety_id == filter_v_id)
    
racks_list = session.exec(query).all()

if search_query:
    q = search_query.lower()
    racks_list = [r for r in racks_list if q in r.rack_identifier.lower() or q in r.metadata_json.lower()]

if racks_list:
    for rack in racks_list:
        v = session.get(Variety, rack.variety_id)
        s = session.get(Species, v.species_id) if v else None
        
        with st.expander(f"🟢 Rack: {rack.rack_identifier} | {v.name if v else 'Unknown'}"):
            col1, col2, col3 = st.columns([1, 2, 1])
            with col1:
                if rack.image_url:
                    st.image(rack.image_url, use_container_width=True)
                else:
                    st.info("No image available.")
            with col2:
                st.write(f"**Species:** {s.name if s else 'N/A'}")
                st.write(f"**Variety:** {v.name if v else 'N/A'}")
                st.write("**Metadata:**")
                meta = rack.metadata_dict
                for k, val in meta.items():
                    st.write(f"- **{k}:** {val}")
            with col3:
                if rack.qr_code_path:
                    st.image(rack.qr_code_path, use_container_width=True)
                    with open(rack.qr_code_path, "rb") as file:
                        st.download_button(
                            label="Download Label",
                            data=file,
                            file_name=f"{rack.rack_identifier}_QR.png",
                            mime="image/png",
                            key=f"dl_{rack.id}"
                        )
                if is_admin():
                    st.write("---")
                    if st.button("Delete Rack", key=f"del_{rack.id}", type="primary"):
                        session.delete(rack)
                        session.commit()
                        log_audit(session, "DELETE", "Rack", rack.id)
                        st.rerun()
else:
    st.info("No racks found matching criteria.")
