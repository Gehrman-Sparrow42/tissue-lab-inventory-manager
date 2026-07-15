import streamlit as st
from sqlmodel import select
from modules.database import get_session, log_audit
from modules.models import Species, Variety, Rack
from modules.auth import is_admin, render_auth_ui
from modules.qr_utils import generate_qr_code
import pandas as pd
import json

st.set_page_config(page_title="Species & Varieties", page_icon="🌿", layout="wide")
render_auth_ui()

st.title("🌿 Species & Varieties Directory")

session = get_session()

if is_admin():
    with st.expander("🛠️ Admin Controls: Add New Entries", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Add Species")
            with st.form("add_species_form"):
                s_name = st.text_input("Species Name")
                s_desc = st.text_area("Description")
                s_meta = st.text_area("Metadata Schema (JSON)", value='[{"name": "pH", "type": "number", "default": 5.5}, {"name": "Light Intensity", "type": "number", "default": 2000}]')
                
                if st.form_submit_button("Save Species"):
                    if not s_name.strip():
                        st.error("Species name cannot be empty.")
                    else:
                        try:
                            json.loads(s_meta)
                            existing = session.exec(select(Species).where(Species.name == s_name)).first()
                            if existing:
                                st.error("Species with this name already exists.")
                            else:
                                new_species = Species(name=s_name, description=s_desc, metadata_schema=s_meta)
                                session.add(new_species)
                                session.commit()
                                # Generate QR
                                new_species.qr_code_path = generate_qr_code(str(new_species.id), "species")
                                session.add(new_species)
                                session.commit()
                                log_audit(session, "CREATE", "Species", new_species.id, s_name)
                                st.success("Species added!")
                                st.rerun()
                        except json.JSONDecodeError:
                            st.error("Invalid JSON format in Metadata Schema.")
                            
        with col2:
            st.subheader("Add Variety")
            species_list = session.exec(select(Species)).all()
            if species_list:
                with st.form("add_variety_form"):
                    v_name = st.text_input("Variety Name")
                    v_species = st.selectbox("Parent Species", [s.id for s in species_list], format_func=lambda x: next((s.name for s in species_list if s.id == x), str(x)))
                    v_desc = st.text_area("Description")
                    if st.form_submit_button("Save Variety"):
                        if not v_name.strip():
                            st.error("Variety name cannot be empty.")
                        else:
                            new_variety = Variety(name=v_name, species_id=v_species, description=v_desc)
                            session.add(new_variety)
                            session.commit()
                            # Generate QR
                            new_variety.qr_code_path = generate_qr_code(str(new_variety.id), "variety")
                            session.add(new_variety)
                            session.commit()
                            log_audit(session, "CREATE", "Variety", new_variety.id, v_name)
                            st.success("Variety added!")
                            st.rerun()
            else:
                st.info("Add a species first.")

st.write("---")
st.subheader("Taxonomy Hierarchy")

species_list = session.exec(select(Species)).all()

if not species_list:
    st.info("No species found. Switch to Admin mode to add some.")
else:
    for s in species_list:
        with st.expander(f"🌿 Species: **{s.name}**", expanded=False):
            col_s1, col_s2 = st.columns([3, 1])
            with col_s1:
                st.write(f"**Description:** {s.description}")
                if is_admin():
                    if st.button("🗑️ Delete Species", key=f"del_s_{s.id}"):
                        varieties_count = len(session.exec(select(Variety).where(Variety.species_id == s.id)).all())
                        if varieties_count > 0:
                            st.error(f"Cannot delete. There are {varieties_count} varieties linked to this species.")
                        else:
                            s_to_del = session.get(Species, s.id)
                            session.delete(s_to_del)
                            session.commit()
                            log_audit(session, "DELETE", "Species", s.id)
                            st.rerun()
            with col_s2:
                if s.qr_code_path:
                    st.image(s.qr_code_path, width=120)
                    with open(s.qr_code_path, "rb") as file:
                        st.download_button(label="Download QR", data=file, file_name=f"Species_{s.id}_QR.png", mime="image/png", key=f"dl_s_{s.id}")
            
            st.write("---")
            st.markdown(f"##### Varieties of {s.name}")
            varieties = session.exec(select(Variety).where(Variety.species_id == s.id)).all()
            
            if not varieties:
                st.info("No varieties registered under this species.")
            else:
                for v in varieties:
                    vcol1, vcol2, vcol3, vcol4, vcol5 = st.columns([2, 3, 2, 2, 2])
                    vcol1.write(f"🌾 **{v.name}**")
                    vcol2.write(f"{v.description if v.description else '-'}")
                    
                    with vcol3:
                        if v.qr_code_path:
                            st.image(v.qr_code_path, width=80)
                    
                    if vcol4.button("➡️ View Racks", key=f"view_r_{v.id}", type="primary"):
                        st.session_state.filter_variety_id = v.id
                        st.switch_page("pages/2_Racks_&_Assets.py")
                        
                    if is_admin():
                        if vcol5.button("🗑️ Delete", key=f"del_v_{v.id}"):
                            racks_count = len(session.exec(select(Rack).where(Rack.variety_id == v.id)).all())
                            if racks_count > 0:
                                st.error(f"Cannot delete. There are {racks_count} racks linked to this variety.")
                            else:
                                v_to_del = session.get(Variety, v.id)
                                session.delete(v_to_del)
                                session.commit()
                                log_audit(session, "DELETE", "Variety", v.id)
                                st.rerun()
