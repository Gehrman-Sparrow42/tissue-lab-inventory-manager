import uuid

import streamlit as st
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import select

from modules.auth import is_admin, render_auth_ui
from modules.database import create_db_and_tables, get_session, log_audit
from modules.models import Rack, Species, Variety, Vessel
from modules.qr_utils import generate_qr_code, get_qr_bytes
from modules.ui import (
    detail_grid,
    empty_state,
    location_trail,
    page_header,
    record_table,
    setup_page,
)

STATUSES = ["Unknown", "Clean", "Contaminated", "Suspected"]


def vessel_fields(prefix, racks, labels, vessel=None):
    rack_ids = [rack.id for rack in racks]
    rack_index = (
        rack_ids.index(vessel.rack_id) if vessel and vessel.rack_id in rack_ids else 0
    )
    st.caption("Location and identity")
    rack_id = st.selectbox(
        "Rack",
        rack_ids,
        index=rack_index,
        format_func=lambda value: labels[value],
        key=f"{prefix}_rack",
    )
    name = st.text_input(
        "Vessel Name (Optional)",
        value=(vessel.name or "") if vessel else "",
        key=f"{prefix}_name",
    )
    st.caption("Culture details")
    passage = st.number_input(
        "Passage Number",
        min_value=0,
        step=1,
        value=vessel.passage_number if vessel else 0,
        key=f"{prefix}_passage",
    )
    medium = st.text_input(
        "Medium Batch (Optional)",
        value=(vessel.medium_batch or "") if vessel else "",
        key=f"{prefix}_medium",
    )
    subculture = st.date_input(
        "Subculture Date (Optional)",
        value=vessel.subculture_date if vessel else None,
        key=f"{prefix}_date",
    )
    statuses = list(STATUSES)
    if vessel and vessel.contamination_status not in statuses:
        statuses.append(vessel.contamination_status)
    status = st.selectbox(
        "Contamination Status",
        statuses,
        index=statuses.index(vessel.contamination_status) if vessel else 0,
        key=f"{prefix}_status",
    )
    notes = st.text_area(
        "Notes (Optional)",
        value=(vessel.notes or "") if vessel else "",
        key=f"{prefix}_notes",
    )
    return {
        "rack_id": rack_id,
        "name": name.strip() or None,
        "passage_number": int(passage),
        "medium_batch": medium.strip() or None,
        "subculture_date": subculture,
        "contamination_status": status,
        "notes": notes.strip() or None,
    }


setup_page("Vessels", active="vessels")
create_db_and_tables()
render_auth_ui()
if st.session_state.get("toast_message"):
    st.toast(st.session_state.pop("toast_message"))
page_header("Vessels", "Find individual vessels, their location and culture details.")
location_trail(["Species", "Varieties", "Racks", "Vessels"])

with get_session() as session:
    racks = session.exec(select(Rack)).all()
    varieties = {v.id: v for v in session.exec(select(Variety)).all()}
    species = {s.id: s for s in session.exec(select(Species)).all()}
    labels = {}
    for rack in racks:
        variety = varieties.get(rack.variety_id)
        parent = species.get(variety.species_id) if variety else None
        labels[rack.id] = (
            f"{parent.name if parent else 'Unknown'} / {variety.name if variety else 'Unknown'} / {rack.rack_identifier}"
        )
    vessels = session.exec(select(Vessel)).all()
    status_options = list(
        dict.fromkeys([*STATUSES, *(v.contamination_status for v in vessels)])
    )
    st.subheader("Find a vessel")
    search_col, filter_col = st.columns([4, 1])
    with search_col:
        search = st.text_input(
            "Search Vessels", placeholder="Search identifiers, names or location"
        )
    with filter_col, st.popover("Filters", use_container_width=True):
        rack_filter = st.selectbox(
            "Filter by rack",
            [None, *labels],
            format_func=lambda value: "All racks" if value is None else labels[value],
            key="vessel_rack_filter",
        )
        status_filter = st.selectbox(
            "Filter by status",
            ["All statuses", *status_options],
            key="vessel_status_filter",
        )
    if search:
        q = search.lower()
        vessels = [
            v
            for v in vessels
            if q
            in " ".join(
                [
                    v.vessel_identifier,
                    v.name or "",
                    v.medium_batch or "",
                    v.contamination_status,
                    v.notes or "",
                    labels.get(v.rack_id, ""),
                ]
            ).lower()
        ]
    if rack_filter is not None:
        vessels = [v for v in vessels if v.rack_id == rack_filter]
    if status_filter != "All statuses":
        vessels = [v for v in vessels if v.contamination_status == status_filter]
    if is_admin() and racks:
        with st.expander("Add New Vessel"), st.form("add_vessel"):
            identifier = st.text_input(
                "Vessel Identifier (Leave blank to auto-generate)"
            )
            values = vessel_fields("new_vessel", racks, labels)
            if st.form_submit_button("Create Vessel"):
                identifier = (
                    identifier.strip() or f"VESSEL-{uuid.uuid4().hex[:8].upper()}"
                )
                try:
                    if session.exec(
                        select(Vessel).where(Vessel.vessel_identifier == identifier)
                    ).first():
                        raise ValueError("Vessel ID already exists.")
                    vessel = Vessel(vessel_identifier=identifier, **values)
                    session.add(vessel)
                    session.flush()
                    log_audit(
                        session,
                        "CREATE",
                        "Vessel",
                        vessel.id,
                        f"Created vessel {identifier} in {labels[values['rack_id']]}",
                    )
                    session.commit()
                except (ValueError, SQLAlchemyError) as exc:
                    session.rollback()
                    st.error(
                        "Vessel ID already exists or the selected rack no longer exists."
                        if isinstance(exc, IntegrityError)
                        else "Database operation failed."
                        if isinstance(exc, SQLAlchemyError)
                        else str(exc)
                    )
                else:
                    st.session_state.toast_message = (
                        f"Vessel '{identifier}' created successfully!"
                    )
                    st.rerun()
    elif is_admin():
        st.info("Create a rack before adding a vessel.")
    st.subheader("Vessel Inventory")
    if vessels:
        st.caption(
            f"{len(vessels)} vessel{'s' if len(vessels) != 1 else ''} shown. Open a record below for details and editing."
        )
        record_table(
            [
                {
                    "level": "vessel",
                    "id": vessel.id,
                    "vessel_identifier": vessel.vessel_identifier,
                    "name": vessel.name,
                    "rack": labels.get(vessel.rack_id, "Unknown rack"),
                    "contamination_status": vessel.contamination_status,
                }
                for vessel in vessels
            ]
        )
    else:
        empty_state(
            "No vessels found",
            "Try another search or filter. Admins can add a vessel to an existing rack.",
        )
    for vessel in vessels:
        with st.expander(
            f"Vessel: {vessel.name + ' (' + vessel.vessel_identifier + ')' if vessel.name else vessel.vessel_identifier}"
        ):
            location_trail(
                [
                    *labels.get(vessel.rack_id, "Unknown rack").split(" / "),
                    vessel.vessel_identifier,
                ]
            )
            detail_grid(
                [
                    ("Vessel ID", vessel.vessel_identifier),
                    ("Location", labels.get(vessel.rack_id, "Unknown rack")),
                    ("Passage number", vessel.passage_number),
                    ("Medium batch", vessel.medium_batch or "—"),
                    ("Subculture date", vessel.subculture_date or "—"),
                    ("Contamination status", vessel.contamination_status),
                    ("Notes", vessel.notes or "—"),
                ]
            )
            try:
                qr_bytes = get_qr_bytes(
                    generate_qr_code(vessel.vessel_identifier, "vessel")
                )
                if qr_bytes:
                    st.image(qr_bytes, width=150)
                    st.download_button(
                        "Download Label",
                        qr_bytes,
                        file_name=f"{vessel.vessel_identifier}_QR.png",
                        mime="image/png",
                        key=f"vessel_qr_{vessel.id}",
                    )
            except (ValueError, OSError) as exc:
                st.error(f"Could not generate vessel label: {exc}")
            if is_admin():
                if racks:
                    with (
                        st.expander("Edit Vessel"),
                        st.form(f"edit_vessel_{vessel.id}"),
                    ):
                        values = vessel_fields(
                            f"edit_vessel_{vessel.id}", racks, labels, vessel
                        )
                        if st.form_submit_button("Save Vessel Changes"):
                            try:
                                for key, value in values.items():
                                    setattr(vessel, key, value)
                                session.add(vessel)
                                session.flush()
                                log_audit(
                                    session,
                                    "UPDATE",
                                    "Vessel",
                                    vessel.id,
                                    f"Edited vessel {vessel.vessel_identifier}; location {labels[values['rack_id']]}",
                                )
                                session.commit()
                            except SQLAlchemyError:
                                session.rollback()
                                st.error("The selected rack no longer exists.")
                            else:
                                st.session_state.toast_message = f"Vessel '{vessel.vessel_identifier}' updated successfully!"
                                st.rerun()

                if st.button("Delete Vessel", key=f"delete_vessel_{vessel.id}"):
                    identifier, record_id = vessel.vessel_identifier, vessel.id
                    try:
                        session.delete(vessel)
                        session.flush()
                        log_audit(
                            session,
                            "DELETE",
                            "Vessel",
                            record_id,
                            f"Deleted vessel {identifier}",
                        )
                        session.commit()
                    except SQLAlchemyError:
                        session.rollback()
                        st.error(
                            "Could not delete this vessel because it is still in use."
                        )
                    else:
                        st.session_state.toast_message = (
                            f"Vessel '{identifier}' deleted."
                        )
                        st.rerun()
