import csv
import io

import streamlit as st
from sqlmodel import select

from modules.auth import is_admin, render_auth_ui
from modules.database import create_db_and_tables, get_session
from modules.exports import _csv_value, inventory_csv, printable_labels
from modules.image_utils import get_image_path
from modules.models import AuditLog, Rack, Species, Variety, Vessel
from modules.qr_utils import generate_qr_code, get_qr_bytes

st.set_page_config(
    page_title="Lab Inventory", layout="wide", initial_sidebar_state="auto"
)
create_db_and_tables()
render_auth_ui()


def show_qr(kind, identifier):
    try:
        path = generate_qr_code(str(identifier), kind)
    except (ValueError, OSError) as exc:
        st.warning(f"QR label unavailable. {exc}")
        return
    st.image(get_qr_bytes(path), width=150, caption="QR code")
    st.download_button(
        "Download QR", get_qr_bytes(path), file_name=f"{kind}_qr.png", mime="image/png"
    )


def scan_view(session, kind, identifier):
    if kind not in {"species", "variety", "rack", "vessel"}:
        st.error("Unknown QR record type. Check the scanned link.")
        return
    if not identifier:
        st.error("The QR link is missing its identifier.")
        return
    if kind in {"species", "variety"}:
        try:
            record_id = int(identifier)
            if not 0 < record_id <= 2**63 - 1:
                raise ValueError
        except ValueError:
            st.error(f"Invalid {kind} ID in the QR link.")
            return
        record = session.get(Species if kind == "species" else Variety, record_id)
    else:
        model = Rack if kind == "rack" else Vessel
        field = Rack.rack_identifier if kind == "rack" else Vessel.vessel_identifier
        record = session.exec(select(model).where(field == identifier)).first()
    if record is None:
        st.error(f"{kind.title()} not found.")
        return
    st.subheader(f"{kind.title()}: {record.name or identifier}")
    if kind == "species":
        st.write(record.description or "No description provided.")
        st.write(
            "Varieties:",
            ", ".join(
                v.name
                for v in session.exec(
                    select(Variety).where(Variety.species_id == record.id)
                ).all()
            )
            or "None",
        )
    elif kind == "variety":
        parent = session.get(Species, record.species_id)
        st.write("Species:", parent.name if parent else "Unknown")
        st.write(record.description or "No description provided.")
        st.write(
            "Racks:",
            ", ".join(
                r.rack_identifier
                for r in session.exec(
                    select(Rack).where(Rack.variety_id == record.id)
                ).all()
            )
            or "None",
        )
    elif kind == "rack":
        variety = session.get(Variety, record.variety_id)
        species = session.get(Species, variety.species_id) if variety else None
        st.write(
            "Species:",
            species.name if species else "Unknown",
            " | Variety:",
            variety.name if variety else "Unknown",
        )
        st.write("Identifier:", record.rack_identifier)
        st.write("Description:", record.description or "None")
        try:
            st.write("Metadata:", record.metadata_dict)
        except ValueError:
            st.warning(
                "This rack has invalid metadata JSON. The original value is shown below for repair."
            )
            st.code(record.metadata_json or "", language="json")
        image = get_image_path(record.image_url)
        if image:
            st.image(image, caption="Rack image", width=300)
    else:
        rack = session.get(Rack, record.rack_id)
        st.write("Identifier:", record.vessel_identifier)
        st.write("Rack:", rack.rack_identifier if rack else "Unknown")
        st.write("Passage number:", record.passage_number)
        st.write("Medium batch:", record.medium_batch or "Not recorded")
        st.write("Subculture date:", str(record.subculture_date or "Not recorded"))
        st.write("Contamination status:", record.contamination_status)
        st.write("Notes:", record.notes or "None")
    show_qr(kind, identifier)


with get_session() as session:
    if "type" in st.query_params or "id" in st.query_params:
        st.title("QR scan result")
        scan_view(
            session, st.query_params.get("type", ""), st.query_params.get("id", "")
        )
        if st.button("Back to dashboard"):
            st.query_params.clear()
            st.rerun()
    else:
        st.title("Laboratory Inventory Management System")
        st.write(
            "Browse species, varieties, racks and vessels using the sidebar. Scan QR labels to open records directly."
        )
        if is_admin():
            st.subheader("Inventory exports")
            st.download_button(
                "Download inventory CSV",
                inventory_csv(session),
                file_name="inventory.csv",
                mime="text/csv",
            )
            try:
                labels = printable_labels(session)
            except (ValueError, OSError) as exc:
                st.warning(f"Printable labels unavailable. {exc}")
            else:
                st.download_button(
                    "Download printable QR labels",
                    labels,
                    file_name="inventory_labels.html",
                    mime="text/html",
                )
            st.subheader("Audit logs")
            logs = session.exec(
                select(AuditLog).order_by(AuditLog.timestamp.desc())
            ).all()
            if logs:
                rows = [
                    {
                        "Timestamp": str(log.timestamp),
                        "Actor label": log.actor or "",
                        "Action": log.action,
                        "Table": log.table_name,
                        "Record ID": log.record_id,
                        "Details": log.details or "",
                    }
                    for log in logs
                ]
                st.dataframe(rows, use_container_width=True)
                output = io.StringIO(newline="")
                writer = csv.DictWriter(output, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(
                    {k: _csv_value(v) for k, v in row.items()} for row in rows
                )
                st.download_button(
                    "Download audit CSV",
                    output.getvalue().encode("utf-8-sig"),
                    file_name="audit_logs.csv",
                    mime="text/csv",
                )
            else:
                st.info("No audit logs found.")
