import streamlit as st
from modules.database import create_db_and_tables, get_session
from modules.models import Species, Variety, Rack
from modules.auth import render_auth_ui
from sqlmodel import select

st.set_page_config(
    page_title="ETAE Lab Inventory",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

create_db_and_tables()
render_auth_ui()

# --- URL ROUTING LOGIC ---
if "type" in st.query_params and "id" in st.query_params:
    e_type = st.query_params["type"]
    e_id = st.query_params["id"]
    
    session = get_session()
    
    st.markdown(f"## 📱 QR Scan Result: {e_type.capitalize()} Information")
    
    if e_type == "rack":
        try:
            rack = session.exec(select(Rack).where(Rack.rack_identifier == e_id)).first()
            if rack:
                v = session.get(Variety, rack.variety_id)
                s = session.get(Species, v.species_id) if v else None
                st.info(f"**Rack ID:** {rack.rack_identifier}")
                col1, col2 = st.columns(2)
                with col1:
                    if rack.image_url:
                        st.image(rack.image_url, use_container_width=True)
                with col2:
                    st.write(f"**Species:** {s.name if s else 'Unknown'}")
                    st.write(f"**Variety:** {v.name if v else 'Unknown'}")
                    st.write("**Metadata:**")
                    for k, val in rack.metadata_dict.items():
                        st.write(f"- {k}: {val}")
                    st.write(f"**Created At:** {rack.created_at.strftime('%Y-%m-%d %H:%M')}")
            else:
                st.error("Rack not found.")
        except Exception:
            st.error("Invalid Rack Identifier or database error.")
            
    elif e_type == "variety":
        try:
            v_id_int = int(e_id)
            v = session.get(Variety, v_id_int)
            if v:
                s = session.get(Species, v.species_id)
                st.info(f"**Variety:** {v.name}")
                st.write(f"**Parent Species:** {s.name if s else 'Unknown'}")
                st.write(f"**Description:** {v.description}")
                st.write("---")
                st.write("### Associated Racks")
                racks = session.exec(select(Rack).where(Rack.variety_id == v.id)).all()
                if racks:
                    for r in racks:
                        st.write(f"- {r.rack_identifier}")
                else:
                    st.write("No racks assigned to this variety.")
            else:
                st.error("Variety not found.")
        except:
            st.error("Invalid Variety ID.")
            
    elif e_type == "species":
        try:
            s_id_int = int(e_id)
            s = session.get(Species, s_id_int)
            if s:
                st.info(f"**Species:** {s.name}")
                st.write(f"**Description:** {s.description}")
                st.write("---")
                st.write("### Registered Varieties")
                varieties = session.exec(select(Variety).where(Variety.species_id == s.id)).all()
                if varieties:
                    for v in varieties:
                        st.write(f"- {v.name}")
                else:
                    st.write("No varieties registered.")
            else:
                st.error("Species not found.")
        except:
            st.error("Invalid Species ID.")

    if st.button("⬅️ Back to Main Dashboard"):
        st.query_params.clear()
        st.rerun()

else:
    st.title("🧬 ETAE Laboratory Inventory Management System")

    st.markdown("""
    Welcome to the **ETAE Hierarchical Laboratory Inventory Management System**.

    ### System Capabilities
    - **Deep Linking QR Codes**: Generate distinct QR codes for Species, Varieties, and individual Racks. Scanning them points directly to their specialized domain pages.
    - **Species & Varieties**: Organize biological subjects hierarchically and define custom metadata schemas for each species.
    - **Racks & Assets**: Register individual physical racks, attach images, and dynamically assign schema-validated metadata.

    ### Quick Start
    Use the sidebar on the left to navigate through the modules.
    """)

    st.info("System operational. Database initialized and connected.")

# Force reload 1
