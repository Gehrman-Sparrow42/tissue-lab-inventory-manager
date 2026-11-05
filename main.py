"""Inventory overview, exports and QR record views."""

import csv
import io

import streamlit as st
from sqlmodel import select

from modules.auth import is_admin, render_auth_ui
from modules.database import create_db_and_tables, get_session
from modules.exports import _csv_value, inventory_csv, inventory_rows, printable_labels
from modules.models import AuditLog, Rack, Species, Variety, Vessel
from modules.qr_utils import generate_qr_code, get_qr_bytes
from modules.ui import (
    detail_grid,
    download_file,
    empty_state,
    location_trail,
    page_header,
    record_table,
    setup_page,
    show_image,
    show_rack_photo,
    status_badge,
)

setup_page("Overview", "overview")
create_db_and_tables()
render_auth_ui()


def show_qr(kind, identifier):
    try:
        data = get_qr_bytes(generate_qr_code(str(identifier), kind))
    except (ValueError, OSError) as exc:
        st.warning(f"QR label unavailable. {exc}")
        return
    show_image(data, width=160, caption="Scan to open this record")
    download_file("Download QR", data, file_name=f"{kind}_qr.png", mime="image/png")


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
        location_trail([record.name])
        st.write(record.description or "No description recorded.")
        children = session.exec(
            select(Variety).where(Variety.species_id == record.id)
        ).all()
        st.subheader("Varieties")
        if children:
            st.dataframe(
                [
                    {"Variety": child.name, "Description": child.description or ""}
                    for child in children
                ],
                hide_index=True,
                use_container_width=True,
            )
        else:
            empty_state(
                "No varieties yet",
                "Create a variety in the species directory to continue the hierarchy.",
            )
    elif kind == "variety":
        parent = session.get(Species, record.species_id)
        location_trail([parent.name if parent else "Unknown species", record.name])
        st.write(record.description or "No description recorded.")
        children = session.exec(select(Rack).where(Rack.variety_id == record.id)).all()
        st.subheader("Racks")
        if children:
            st.dataframe(
                [
                    {"Identifier": child.rack_identifier, "Name": child.name or ""}
                    for child in children
                ],
                hide_index=True,
                use_container_width=True,
            )
        else:
            empty_state(
                "No racks assigned",
                "Open the rack inventory to add a rack to this variety.",
            )
    elif kind == "rack":
        variety = session.get(Variety, record.variety_id)
        species = session.get(Species, variety.species_id) if variety else None
        location_trail(
            [
                species.name if species else "Unknown species",
                variety.name if variety else "Unknown variety",
                record.rack_identifier,
            ]
        )
        details, photo = st.columns([2, 1])
        with details:
            detail_grid(
                [
                    ("Rack identifier", record.rack_identifier),
                    ("Name", record.name),
                    ("Species", species.name if species else None),
                    ("Variety", variety.name if variety else None),
                ]
            )
            if record.description:
                st.write(record.description)
        with photo:
            show_rack_photo(
                record.image_url, caption="Rack image", use_container_width=True
            )
        st.subheader("Metadata")
        try:
            metadata = record.metadata_dict
            if metadata:
                detail_grid(list(metadata.items()))
            else:
                st.caption("No metadata recorded.")
        except ValueError:
            st.warning(
                "This rack has invalid metadata JSON. An administrator can repair it in the rack inventory."
            )
            st.code(record.metadata_json or "", language="json")
        vessels = session.exec(select(Vessel).where(Vessel.rack_id == record.id)).all()
        if vessels:
            st.subheader("Vessels in this rack")
            st.dataframe(
                [
                    {
                        "Identifier": vessel.vessel_identifier,
                        "Name": vessel.name or "",
                        "Status": vessel.contamination_status,
                    }
                    for vessel in vessels
                ],
                hide_index=True,
                use_container_width=True,
            )
    else:
        rack = session.get(Rack, record.rack_id)
        variety = session.get(Variety, rack.variety_id) if rack else None
        species = session.get(Species, variety.species_id) if variety else None
        location_trail(
            [
                species.name if species else "Unknown species",
                variety.name if variety else "Unknown variety",
                rack.rack_identifier if rack else "Unknown rack",
                record.vessel_identifier,
            ]
        )
        status_badge(record.contamination_status)
        detail_grid(
            [
                ("Vessel identifier", record.vessel_identifier),
                ("Rack", rack.rack_identifier if rack else None),
                ("Passage number", record.passage_number),
                ("Medium batch", record.medium_batch),
                ("Subculture date", record.subculture_date),
                ("Name", record.name),
            ]
        )
        if record.notes:
            st.subheader("Notes")
            st.write(record.notes)
    with st.expander("QR label"):
        show_qr(kind, identifier)


def audit_rows(session):
    logs = session.exec(select(AuditLog).order_by(AuditLog.timestamp.desc())).all()
    return [
        {
            "Timestamp (UTC)": str(log.timestamp),
            "Operator label": log.actor or "",
            "Action": log.action,
            "Record type": log.table_name,
            "Record ID": log.record_id,
            "Details": log.details or "",
        }
        for log in logs
    ]


def overview(session):
    heading, action = st.columns([4, 1])
    with heading:
        page_header(
            "Inventory workspace",
            "Find records, follow their location, and keep your collection current.",
        )
    with action:
        if st.button("Browse racks", type="primary", use_container_width=True):
            st.switch_page("pages/2_Racks_&_Assets.py")
    rows = inventory_rows(session)
    counts = {
        kind: sum(row["level"] == kind for row in rows)
        for kind in ("species", "variety", "rack", "vessel")
    }
    location_trail(
        [
            f"{counts['species']} species",
            f"{counts['variety']} varieties",
            f"{counts['rack']} racks",
            f"{counts['vessel']} vessels",
        ]
    )
    st.subheader("Find a record")
    search_column, kind_column, sort_column = st.columns([3, 1.2, 1.3])
    search = search_column.text_input(
        "Search inventory",
        placeholder="Identifier, name, location or metadata",
        key="workspace_search",
    )
    selected_type = kind_column.selectbox(
        "Record type",
        ["All records", "Species", "Varieties", "Racks", "Vessels"],
        key="workspace_type",
    )
    order = sort_column.selectbox(
        "Sort by", ["Name A–Z", "Newest first", "Type"], key="workspace_order"
    )
    kind = {
        "Species": "species",
        "Varieties": "variety",
        "Racks": "rack",
        "Vessels": "vessel",
    }.get(selected_type)
    matches = rows
    if kind:
        matches = [row for row in matches if row["level"] == kind]
    if search.strip():
        query = search.strip().casefold()
        matches = [
            row
            for row in matches
            if query
            in " ".join(
                str(value) for value in row.values() if value is not None
            ).casefold()
        ]
    if order == "Newest first":
        matches = sorted(
            matches, key=lambda row: str(row.get("created_at", "")), reverse=True
        )
    elif order == "Type":
        matches = sorted(
            matches,
            key=lambda row: (
                row["level"],
                str(row.get("name") or row.get("id")).casefold(),
            ),
        )
    else:
        matches = sorted(
            matches,
            key=lambda row: str(
                row.get("name")
                or row.get("rack_identifier")
                or row.get("vessel_identifier")
                or row["id"]
            ).casefold(),
        )
    show_all = st.session_state.get("workspace_all", False)
    visible = matches if show_all else matches[:6]
    record_table(visible)
    st.caption(
        f"Showing {len(visible)} of {len(matches)} matching records. Select a record name to open its details in a new tab."
    )
    if len(matches) > 6:
        st.checkbox("Show all matches", key="workspace_all")
    if not rows:
        empty_state(
            "Start your collection with a species",
            "The species directory defines the hierarchy and metadata for your racks. Sign in with admin access to add records.",
        )
    elif not matches:
        st.info("Try another search or change the record type to see more results.")
    directory, supporting = st.columns([1, 1.7], gap="large")
    with directory:
        st.subheader("Collection directory")
        st.page_link("pages/1_Species_&_Varieties.py", label="Species & varieties")
        st.caption(f"{counts['species']} species and {counts['variety']} varieties")
        st.page_link("pages/2_Racks_&_Assets.py", label="Racks & assets")
        st.caption(f"{counts['rack']} racks with photos and metadata")
        st.page_link("pages/3_Vessels.py", label="Vessels")
        st.caption(f"{counts['vessel']} vessels with culture records")
    with supporting:
        if is_admin():
            activity, downloads = st.tabs(["Recent activity", "Downloads"])
            logs = audit_rows(session)
            with activity:
                if logs:
                    st.dataframe(logs[:5], hide_index=True, use_container_width=True)
                    with st.expander("Full audit history"):
                        st.dataframe(logs, hide_index=True, use_container_width=True)
                else:
                    st.caption(
                        "Changes will appear here after records are created or updated."
                    )
            with downloads:
                download_file(
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
                    download_file(
                        "Download printable QR labels",
                        labels,
                        file_name="inventory_labels.html",
                        mime="text/html",
                    )
                if logs:
                    output = io.StringIO(newline="")
                    writer = csv.DictWriter(output, fieldnames=list(logs[0]))
                    writer.writeheader()
                    writer.writerows(
                        {key: _csv_value(value) for key, value in row.items()}
                        for row in logs
                    )
                    download_file(
                        "Download audit CSV",
                        output.getvalue().encode("utf-8-sig"),
                        file_name="audit_logs.csv",
                        mime="text/csv",
                    )
                st.caption(
                    "Prepare a database snapshot from the backup controls in the sidebar."
                )
        else:
            st.subheader("Open a scanned record")
            st.write(
                "Scan a printed QR label with your phone camera to open the matching species, variety, rack or vessel."
            )
            st.caption(
                "Browsing is available without signing in. Admin access enables editing and downloads."
            )


with get_session() as session:
    if "type" in st.query_params or "id" in st.query_params:
        page_header("Record details", "Inventory information from your scanned label.")
        scan_view(
            session, st.query_params.get("type", ""), st.query_params.get("id", "")
        )
        if st.button("Back to dashboard"):
            st.query_params.clear()
            st.rerun()
    else:
        overview(session)
