import hashlib
import json
import uuid
from collections import Counter

import streamlit as st
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import select

from modules.auth import is_admin, render_auth_ui
from modules.database import create_db_and_tables, get_session, log_audit
from modules.image_utils import (
    get_image_path,
    normalize_image_reference,
    process_and_save_image,
    safe_remove_file,
)
from modules.metadata_ui import render_metadata_fields
from modules.models import Rack, Species, Variety, Vessel
from modules.qr_utils import generate_qr_code, get_qr_bytes
from modules.ui import (
    detail_grid,
    download_file,
    empty_state,
    location_trail,
    page_header,
    setup_page,
    show_image,
)
from modules.validation import validate_metadata_values


def metadata_prefix(prefix, variety_id, schema):
    return f"{prefix}_{variety_id}_{hashlib.sha256(schema.encode()).hexdigest()[:12]}"


def remove_unreferenced_image(session, path):
    managed_path = normalize_image_reference(path)
    if managed_path is None:
        return
    saved_paths = session.exec(select(Rack.image_url)).all()
    if not any(
        normalize_image_reference(saved) == managed_path for saved in saved_paths
    ):
        safe_remove_file(managed_path)


def metadata_fields(schema, current, prefix):
    try:
        return render_metadata_fields(schema, current, prefix)
    except (ValueError, TypeError) as exc:
        st.error(f"Invalid metadata schema: {exc}")
        return None


setup_page("Racks & Assets", active="racks")
create_db_and_tables()
render_auth_ui()
if st.session_state.get("toast_message"):
    st.toast(st.session_state.pop("toast_message"))
page_header("Racks & assets", "Browse rack locations, metadata and labels.")
location_trail(["Species", "Varieties", "Racks"])

with get_session() as session:
    filter_v_id = st.session_state.get("filter_variety_id")
    varieties = session.exec(select(Variety)).all()
    varieties_by_id = {v.id: v for v in varieties}
    species_by_id = {s.id: s for s in session.exec(select(Species)).all()}
    ids = [v.id for v in varieties]
    variety_labels = {}
    for variety in varieties:
        species = species_by_id.get(variety.species_id)
        variety_labels[variety.id] = (
            f"{species.name if species else 'Unknown'} / {variety.name}"
        )
    label_counts = Counter(variety_labels.values())
    for variety_id, label in variety_labels.items():
        if label_counts[label] > 1:
            variety_labels[variety_id] = f"{label} (ID {variety_id})"

    def variety_label(variety_id):
        return variety_labels[variety_id]

    if filter_v_id in varieties_by_id:
        st.success(
            f"Currently viewing racks for Variety: **{varieties_by_id[filter_v_id].name}**"
        )
        if st.button("Clear Filter to Show All Racks"):
            st.session_state.filter_variety_id = None
            st.rerun()
    elif filter_v_id:
        filter_v_id = None
    st.subheader("Find a rack")
    search_col, filter_col = st.columns([3, 2])
    with search_col:
        search = st.text_input(
            "Global Search (Rack ID, Metadata)",
            "",
            placeholder="Search identifiers, names or metadata",
        )
    with filter_col:
        selected_filter = st.selectbox(
            "Filter by variety",
            [None, *ids],
            format_func=lambda value: (
                "All varieties" if value is None else variety_label(value)
            ),
            key="rack_inventory_variety_filter",
        )

    if is_admin() and varieties:
        with st.expander("Add New Rack"):
            variety_id = st.selectbox(
                "Select Variety for New Rack",
                ids,
                index=ids.index(filter_v_id) if filter_v_id in ids else 0,
                format_func=variety_label,
            )
            species = species_by_id.get(varieties_by_id[variety_id].species_id)
            if species:
                schema = species.metadata_schema
                with st.form("add_rack_form"):
                    st.caption("Rack details")
                    identifier = st.text_input(
                        "Rack Identifier (Leave blank to auto-generate)"
                    )
                    name = st.text_input("Rack Name (Optional)")
                    description = st.text_area("Rack Description (Optional)")
                    st.write(f"**Metadata Configuration for {species.name}**")
                    values = metadata_fields(
                        schema, {}, metadata_prefix("new", variety_id, schema)
                    )
                    upload = st.file_uploader(
                        "Upload Rack Image", type=["jpg", "jpeg", "png"]
                    )
                    if st.form_submit_button("Create Rack") and values is not None:
                        image = None
                        try:
                            values = validate_metadata_values(values, schema)
                            identifier = (
                                identifier.strip()
                                or f"RACK-{uuid.uuid4().hex[:8].upper()}"
                            )
                            if session.exec(
                                select(Rack).where(Rack.rack_identifier == identifier)
                            ).first():
                                raise ValueError("Rack ID already exists.")
                            image = process_and_save_image(upload) if upload else None
                            rack = Rack(
                                rack_identifier=identifier,
                                variety_id=variety_id,
                                name=name.strip() or None,
                                description=description.strip() or None,
                                image_url=image,
                                qr_code_path=generate_qr_code(identifier, "rack"),
                                metadata_json=json.dumps(values),
                            )
                            session.add(rack)
                            session.flush()
                            log_audit(
                                session,
                                "CREATE",
                                "Rack",
                                rack.id,
                                f"Created rack {identifier}",
                            )
                            session.commit()
                        except (ValueError, SQLAlchemyError, OSError) as exc:
                            session.rollback()
                            if image:
                                remove_unreferenced_image(session, image)
                            st.error(
                                "Rack ID already exists or the selected variety no longer exists."
                                if isinstance(exc, IntegrityError)
                                else "Database operation failed."
                                if isinstance(exc, SQLAlchemyError)
                                else str(exc)
                            )
                        else:
                            st.session_state.toast_message = (
                                f"Rack '{identifier}' created successfully!"
                            )
                            st.rerun()
            else:
                st.error("The selected variety has no species.")

    st.subheader("Rack Inventory")
    query = select(Rack)
    if filter_v_id:
        query = query.where(Rack.variety_id == filter_v_id)
    if selected_filter is not None:
        query = query.where(Rack.variety_id == selected_filter)
    racks = session.exec(query).all()
    if search:
        q = search.lower()
        racks = [
            r
            for r in racks
            if q
            in " ".join(
                [r.rack_identifier, r.name or "", r.description or "", r.metadata_json]
            ).lower()
        ]
    if racks:
        st.caption(
            f"{len(racks)} rack{'s' if len(racks) != 1 else ''} shown. Open a record below for details and editing."
        )
        st.dataframe(
            [
                {
                    "Rack ID": r.rack_identifier,
                    "Name": r.name or "—",
                    "Location": variety_labels.get(r.variety_id, "Unknown"),
                }
                for r in racks
            ],
            hide_index=True,
            use_container_width=True,
        )
    else:
        empty_state(
            "No racks found",
            "Try another search or variety. Admins can add a rack when a variety exists.",
        )
    for rack in racks:
        variety = varieties_by_id.get(rack.variety_id)
        species = species_by_id.get(variety.species_id) if variety else None
        label = (
            f"{rack.name} ({rack.rack_identifier})"
            if rack.name
            else rack.rack_identifier
        )
        try:
            current_metadata = rack.metadata_dict
            metadata_error = None
        except ValueError as exc:
            current_metadata = None
            metadata_error = str(exc)
        with st.expander(f"Rack: {label} | {variety.name if variety else 'Unknown'}"):
            if metadata_error:
                st.error(
                    f"Invalid saved metadata: {metadata_error}. Repair the raw metadata before editing this rack."
                )
                st.code(rack.metadata_json)
                if is_admin():
                    with st.form(f"repair_metadata_{rack.id}"):
                        replacement = st.text_area(
                            "Corrected Metadata (JSON)",
                            value=rack.metadata_json,
                            key=f"repair_raw_{rack.id}",
                        )
                        st.caption(
                            "Save a JSON object. The original raw value will be retained in the audit log."
                        )
                        if st.form_submit_button("Repair Metadata"):
                            try:
                                repaired = json.loads(replacement)
                                if not isinstance(repaired, dict):
                                    raise ValueError(  # noqa: TRY004 — invalid submitted JSON uses ValueError
                                        "Corrected metadata must be a JSON object."
                                    )
                                original_raw = rack.metadata_json
                                rack.metadata_json = json.dumps(
                                    repaired, ensure_ascii=False, allow_nan=False
                                )
                                log_audit(
                                    session,
                                    "REPAIR",
                                    "Rack",
                                    rack.id,
                                    json.dumps(
                                        {
                                            "rack_identifier": rack.rack_identifier,
                                            "original_metadata": original_raw,
                                            "replacement_metadata": repaired,
                                        },
                                        ensure_ascii=False,
                                    ),
                                )
                                session.commit()
                            except (ValueError, SQLAlchemyError) as exc:
                                session.rollback()
                                st.error(
                                    "Metadata repair could not be saved. Try again."
                                    if isinstance(exc, SQLAlchemyError)
                                    else str(exc)
                                )
                            else:
                                st.session_state.toast_message = f"Metadata repaired for rack '{rack.rack_identifier}'."
                                st.rerun()
            location_trail(
                [
                    species.name if species else "Unknown species",
                    variety.name if variety else "Unknown variety",
                    rack.rack_identifier,
                ]
            )
            col1, col2, col3 = st.columns([1, 2, 1])
            with col1:
                image_path = get_image_path(rack.image_url)
                if image_path:
                    show_image(image_path)
                else:
                    st.caption("No image available")
            with col2:
                detail_grid(
                    [
                        ("Rack ID", rack.rack_identifier),
                        ("Name", rack.name or "—"),
                        ("Species", species.name if species else "N/A"),
                        ("Variety", variety.name if variety else "N/A"),
                        ("Description", rack.description or "—"),
                    ]
                )
                st.write("**Metadata:**")
                for key, value in (current_metadata or {}).items():
                    st.write(f"- **{key}:** {value}")
            with col3:
                try:
                    qr = generate_qr_code(rack.rack_identifier, "rack")
                    qr_bytes = get_qr_bytes(qr)
                except (ValueError, OSError) as exc:
                    qr_bytes = b""
                    st.error(f"Could not generate rack label: {exc}")
                if qr_bytes:
                    show_image(qr_bytes, width=150)
                    download_file(
                        "Download Label",
                        qr_bytes,
                        file_name=f"{rack.rack_identifier}_QR.png",
                        mime="image/png",
                        key=f"dl_{rack.id}",
                    )
            if is_admin() and ids and current_metadata is not None:
                with st.expander("Edit"):
                    selected_id = st.selectbox(
                        "Select Variety",
                        ids,
                        index=ids.index(rack.variety_id)
                        if rack.variety_id in ids
                        else 0,
                        format_func=variety_label,
                        key=f"edit_variety_{rack.id}",
                    )
                    selected_species = species_by_id.get(
                        varieties_by_id[selected_id].species_id
                    )
                    if selected_species:
                        schema = selected_species.metadata_schema
                        with st.form(f"edit_rack_form_{rack.id}"):
                            name = st.text_input(
                                "Rack Name",
                                value=rack.name or "",
                                key=f"edit_name_{rack.id}",
                            )
                            description = st.text_area(
                                "Rack Description",
                                value=rack.description or "",
                                key=f"edit_desc_{rack.id}",
                            )
                            st.write("**Metadata**")
                            st.caption(
                                "Existing fields outside this schema are retained."
                            )
                            values = metadata_fields(
                                schema,
                                current_metadata,
                                metadata_prefix(f"edit_{rack.id}", selected_id, schema),
                            )
                            upload = st.file_uploader(
                                "Replace Rack Image",
                                type=["jpg", "jpeg", "png"],
                                key=f"edit_img_{rack.id}",
                            )
                            if (
                                st.form_submit_button("Save Changes")
                                and values is not None
                            ):
                                image = None
                                old_image = rack.image_url
                                try:
                                    values = validate_metadata_values(values, schema)
                                    image = (
                                        process_and_save_image(upload)
                                        if upload
                                        else None
                                    )
                                    rack.variety_id = selected_id
                                    rack.name = name.strip() or None
                                    rack.description = description.strip() or None
                                    rack.metadata_json = json.dumps(values)
                                    if image:
                                        rack.image_url = image
                                    session.add(rack)
                                    session.flush()
                                    log_audit(
                                        session,
                                        "UPDATE",
                                        "Rack",
                                        rack.id,
                                        f"Edited rack {rack.rack_identifier}",
                                    )
                                    session.commit()
                                except (ValueError, SQLAlchemyError, OSError) as exc:
                                    session.rollback()
                                    if image:
                                        remove_unreferenced_image(session, image)
                                    st.error(
                                        "The selected variety no longer exists."
                                        if isinstance(exc, IntegrityError)
                                        else "Database operation failed."
                                        if isinstance(exc, SQLAlchemyError)
                                        else str(exc)
                                    )
                                else:
                                    if image and old_image != image:
                                        remove_unreferenced_image(session, old_image)
                                    st.session_state.toast_message = f"Rack '{rack.rack_identifier}' updated successfully!"
                                    st.rerun()
                    else:
                        st.error("The selected variety has no species.")

            if is_admin() and st.button(
                "Delete Rack",
                key=f"del_{rack.id}",
                help="Permanently delete an empty rack.",
            ):
                if session.exec(
                    select(Vessel).where(Vessel.rack_id == rack.id)
                ).first():
                    st.error(
                        "Cannot delete a rack containing vessels. Move or delete its vessels first."
                    )
                else:
                    identifier, image, record_id = (
                        rack.rack_identifier,
                        rack.image_url,
                        rack.id,
                    )
                    try:
                        session.delete(rack)
                        session.flush()
                        log_audit(
                            session,
                            "DELETE",
                            "Rack",
                            record_id,
                            f"Deleted rack {identifier}",
                        )
                        session.commit()
                    except SQLAlchemyError:
                        session.rollback()
                        st.error("Cannot delete this rack because it is still in use.")
                    else:
                        remove_unreferenced_image(session, image)
                        st.session_state.toast_message = f"Rack '{identifier}' deleted."
                        st.rerun()
