import streamlit as st
from modules.database import create_db_and_tables, get_session
from modules.models import Species, Variety, Rack, AuditLog
from modules.auth import render_auth_ui, is_admin
from sqlmodel import select
import pandas as pd

st.set_page_config(
    page_title="ETAE Lab Inventory",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded"
)

create_db_and_tables()
render_auth_ui()

# Route QR parameters
if "type" in st.query_params and "id" in st.query_params:
    e_type = st.query_params["type"]
    e_id = st.query_params["id"]
    
    session = get_session()
    
    st.markdown(f"## QR Scan Result: {e_type.capitalize()} Information")
    
    if e_type == "rack":
        try:
            rack = session.exec(select(Rack).where(Rack.rack_identifier == e_id)).first()
            if rack:
                v = session.get(Variety, rack.variety_id)
                s = session.get(Species, v.species_id) if v else None
                st.info(f"**Rack:** {rack.name if rack.name else rack.rack_identifier}")
                col1, col2, col3 = st.columns([1, 1, 1])
                with col1:
                    st.info("Image Here")
                with col2:
                    st.write(f"**Rack ID:** {rack.rack_identifier}")
                    st.write(f"**Description:** {rack.description if rack.description else 'No description provided.'}")
                    st.write(f"**Species:** {s.name if s else 'Unknown'}")
                    st.write(f"**Variety:** {v.name if v else 'Unknown'}")
                    st.write("**Metadata:**")
                    for k, val in rack.metadata_dict.items():
                        st.write(f"- {k}: {val}")
                    st.write(f"**Created At:** {rack.created_at.strftime('%Y-%m-%d %H:%M')}")
                with col3:
                    from modules.qr_utils import generate_qr_code, get_qr_bytes
                    qr_url = generate_qr_code(rack.rack_identifier, "rack")
                    st.image(qr_url, width=150, caption="QR Code")
                    qr_bytes = get_qr_bytes(qr_url)
                    if qr_bytes:
                        st.download_button(label="Download QR", data=qr_bytes, file_name=f"Rack_{rack.rack_identifier}_QR.png", mime="image/png", key="dl_qr_rack")
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
                col1, col2 = st.columns([2, 1])
                with col1:
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
                with col2:
                    from modules.qr_utils import generate_qr_code, get_qr_bytes
                    qr_url = generate_qr_code(str(v.id), "variety")
                    st.image(qr_url, width=150, caption="QR Code")
                    qr_bytes = get_qr_bytes(qr_url)
                    if qr_bytes:
                        st.download_button(label="Download QR", data=qr_bytes, file_name=f"Variety_{v.id}_QR.png", mime="image/png", key="dl_qr_var")
            else:
                st.error("Variety not found.")
        except:
            st.error("Invalid Variety ID.")
            
    elif e_type == "species":
        try:
            s_id_int = int(e_id)
            s = session.get(Species, s_id_int)
            if s:
                col1, col2 = st.columns([2, 1])
                with col1:
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
                with col2:
                    from modules.qr_utils import generate_qr_code, get_qr_bytes
                    qr_url = generate_qr_code(str(s.id), "species")
                    st.image(qr_url, width=150, caption="QR Code")
                    qr_bytes = get_qr_bytes(qr_url)
                    if qr_bytes:
                        st.download_button(label="Download QR", data=qr_bytes, file_name=f"Species_{s.id}_QR.png", mime="image/png", key="dl_qr_spec")
            else:
                st.error("Species not found.")
        except:
            st.error("Invalid Species ID.")

    if st.button("Back to Main Dashboard"):
        st.query_params.clear()
        st.rerun()

else:
    st.title("ETAE Laboratory Inventory Management System")

    def render_overview():
        st.markdown("""
        Welcome to the ETAE Laboratory Inventory Management System.

        ### Features
        - **QR Codes**: Generate QR code sheets for Species, Varieties, and Racks to access details instantly.
        - **Species & Varieties**: Define testing categories and custom metadata schemas.
        - **Racks & Assets**: Track containers and log dynamic metadata values.

        ### Navigation
        Use the sidebar menu to navigate.
        """)
        st.info("System operational. Database connected.")

    if is_admin():
        tab1, tab2 = st.tabs(["Dashboard Overview", "Admin Audit Logs"])
        with tab1:
            render_overview()
        with tab2:
            st.subheader("System Audit Logs")
            session = get_session()
            logs = session.exec(select(AuditLog).order_by(AuditLog.timestamp.desc())).all()
            if logs:
                log_data = []
                for l in logs:
                    log_data.append({
                        "Timestamp": l.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        "Action": l.action,
                        "Table": l.table_name,
                        "Record ID": l.record_id,
                        "Details": l.details
                    })
                df = pd.DataFrame(log_data)
                st.dataframe(df, use_container_width=True)
                
                # Export to CSV
                csv_data = df.to_csv(index=False).encode("utf-8")
                from datetime import datetime
                st.download_button(
                    label="Export Audit Logs as CSV",
                    data=csv_data,
                    file_name=f"audit_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    key="export_audit_logs"
                )
            else:
                st.info("No audit logs found.")
    else:
        render_overview()
