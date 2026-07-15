import streamlit as st
from sqlmodel import select
from modules.database import get_session, log_audit
from modules.models import Species, Variety, Rack
from modules.auth import is_admin, render_auth_ui
from modules.qr_utils import generate_qr_code
from modules.image_utils import process_and_save_image
import json
import uuid

st.set_page_config(page_title="Racks & Assets", page_icon=None, layout="wide")
render_auth_ui()

# Display persistent toast feedback if any
if "toast_message" in st.session_state and st.session_state.toast_message:
    st.toast(st.session_state.toast_message)
    del st.session_state.toast_message

st.title("Racks & Assets Management")

session = get_session()

# Handling interconnected filtering
filter_v_id = st.session_state.get("filter_variety_id", None)
if filter_v_id:
    v_obj = session.get(Variety, filter_v_id)
    if v_obj:
        st.success(f"Currently viewing racks for Variety: **{v_obj.name}**")
        if st.button("Clear Filter to Show All Racks"):
            st.session_state.filter_variety_id = None
            st.session_state.toast_message = "Filter cleared."
            st.rerun()
        st.write("---")

search_query = st.text_input("Global Search (Rack ID, Metadata)", "")

with st.spinner("Loading database records..."):
    varieties_list = session.exec(select(Variety)).all()
    varieties_dict = {v.id: v for v in varieties_list}
    species_dict = {s.id: s for s in session.exec(select(Species)).all()}

if is_admin() and varieties_list:
    with st.expander("Add New Rack", expanded=False):
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
                r_name = st.text_input("Rack Name (Optional)")
                r_desc = st.text_area("Rack Description (Optional)")
                
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
                            name=r_name.strip() if r_name.strip() else None,
                            description=r_desc.strip() if r_desc.strip() else None,
                            qr_code_path=qr_path,
                            image_url=img_path,
                            metadata_json=json.dumps(meta_values)
                        )
                        session.add(new_rack)
                        session.commit()
                        log_audit(session, "CREATE", "Rack", new_rack.id, r_id)
                        st.session_state.toast_message = f"Rack '{r_id}' created successfully!"
                        st.rerun()

st.subheader("Rack Inventory")

query = select(Rack)
if filter_v_id:
    query = query.where(Rack.variety_id == filter_v_id)
    
with st.spinner("Loading racks..."):
    racks_list = session.exec(query).all()

if search_query:
    q = search_query.lower()
    racks_list = [
        r for r in racks_list 
        if q in r.rack_identifier.lower() 
        or (r.name and q in r.name.lower())
        or (r.description and q in r.description.lower())
        or any(q in str(val).lower() for val in r.metadata_dict.values())
    ]

if racks_list:
    for rack in racks_list:
        v = varieties_dict.get(rack.variety_id)
        s = species_dict.get(v.species_id) if v else None
        
        rack_label = f"{rack.name} ({rack.rack_identifier})" if rack.name else rack.rack_identifier
        with st.expander(f"Rack: {rack_label} | {v.name if v else 'Unknown'}"):
            col1, col2, col3 = st.columns([1, 2, 1])
            with col1:
                st.info("Image Here")
            with col2:
                st.write(f"**Rack ID:** {rack.rack_identifier}")
                if rack.name:
                    st.write(f"**Name:** {rack.name}")
                if rack.description:
                    st.write(f"**Description:** {rack.description}")
                st.write(f"**Species:** {s.name if s else 'N/A'}")
                st.write(f"**Variety:** {v.name if v else 'N/A'}")
                st.write("**Metadata:**")
                meta = rack.metadata_dict
                for k, val in meta.items():
                    st.write(f"- **{k}:** {val}")
            with col3:
                from modules.qr_utils import generate_qr_code, get_qr_bytes
                qr_url = generate_qr_code(rack.rack_identifier, "rack")
                st.image(qr_url, width=150)
                qr_bytes = get_qr_bytes(qr_url)
                if qr_bytes:
                    st.download_button(
                        label="Download Label",
                        data=qr_bytes,
                        file_name=f"{rack.rack_identifier}_QR.png",
                        mime="image/png",
                        key=f"dl_{rack.id}"
                    )
                if is_admin():
                    st.write("---")
                    col_del, col_edit = st.columns(2)
                    with col_del:
                        if st.button("Delete Rack", key=f"del_{rack.id}", type="primary"):
                            rack_id_str = rack.rack_identifier
                            rack_img = rack.image_url
                            rack_qr = rack.qr_code_path
                            session.delete(rack)
                            session.commit()
                            log_audit(session, "DELETE", "Rack", rack.id)
                            from modules.image_utils import safe_remove_file
                            safe_remove_file(rack_img)
                            safe_remove_file(rack_qr)
                            st.session_state.toast_message = f"Rack '{rack_id_str}' deleted."
                            st.rerun()
                    with col_edit:
                        with st.expander("Edit"):
                            with st.form(f"edit_rack_form_{rack.id}"):
                                edit_r_variety = st.selectbox(
                                    "Select Variety",
                                    [v_item.id for v_item in varieties_list],
                                    index=[v_item.id for v_item in varieties_list].index(rack.variety_id) if rack.variety_id in [v_item.id for v_item in varieties_list] else 0,
                                    format_func=lambda x: next((v_item.name for v_item in varieties_list if v_item.id == x), str(x)),
                                    key=f"edit_variety_{rack.id}"
                                )
                                edit_r_name = st.text_input("Rack Name", value=rack.name if rack.name else "", key=f"edit_name_{rack.id}")
                                edit_r_desc = st.text_area("Rack Description", value=rack.description if rack.description else "", key=f"edit_desc_{rack.id}")
                                
                                ev_obj = session.get(Variety, edit_r_variety)
                                es_obj = session.get(Species, ev_obj.species_id) if ev_obj else None
                                
                                edit_schema = []
                                if es_obj:
                                    try:
                                        edit_schema = json.loads(es_obj.metadata_schema)
                                    except:
                                        pass
                                
                                st.write("**Edit Metadata**")
                                edit_meta_values = {}
                                ecols = st.columns(2)
                                current_meta = rack.metadata_dict
                                
                                for i, field in enumerate(edit_schema):
                                    fname = field.get("name", f"Field {i}")
                                    ftype = field.get("type", "text")
                                    current_val = current_meta.get(fname, field.get("default", ""))
                                    
                                    with ecols[i % 2]:
                                        if ftype == "number":
                                            try:
                                                def_val = float(current_val)
                                            except:
                                                def_val = 0.0
                                            edit_meta_values[fname] = st.number_input(fname, value=def_val, key=f"edit_field_{fname}_{rack.id}")
                                        else:
                                            edit_meta_values[fname] = st.text_input(fname, value=str(current_val), key=f"edit_field_{fname}_{rack.id}")
                                
                                edit_r_image = st.file_uploader("Replace Rack Image", type=['jpg', 'jpeg', 'png'], key=f"edit_img_{rack.id}")
                                
                                if st.form_submit_button("Save Changes"):
                                    rack_to_edit = session.get(Rack, rack.id)
                                    rack_to_edit.variety_id = edit_r_variety
                                    rack_to_edit.name = edit_r_name.strip() if edit_r_name.strip() else None
                                    rack_to_edit.description = edit_r_desc.strip() if edit_r_desc.strip() else None
                                    rack_to_edit.metadata_json = json.dumps(edit_meta_values)
                                    
                                    if edit_r_image:
                                        old_img = rack_to_edit.image_url
                                        img_path = process_and_save_image(edit_r_image)
                                        rack_to_edit.image_url = img_path
                                        if old_img:
                                            from modules.image_utils import safe_remove_file
                                            safe_remove_file(old_img)
                                        
                                    session.add(rack_to_edit)
                                    session.commit()
                                    log_audit(session, "UPDATE", "Rack", rack.id, f"Edited: {rack.rack_identifier}")
                                    st.session_state.toast_message = f"Rack '{rack.rack_identifier}' updated successfully!"
                                    st.rerun()
else:
    st.info("No racks found matching criteria.")
