import json

import streamlit as st
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import select

from modules.auth import is_admin, render_auth_ui
from modules.database import create_db_and_tables, get_session, log_audit
from modules.models import Rack, Species, Variety
from modules.qr_utils import generate_qr_code, get_qr_bytes
from modules.validation import (
    migrate_racks_metadata,
    reconcile_metadata,
    validate_metadata_schema,
)


def species_duplicate(session, name, exclude_id=None):
    return any(
        item.id != exclude_id and item.name.strip() == name
        for item in session.exec(select(Species)).all()
    )


def variety_duplicate(session, name, species_id, exclude_id=None):
    varieties = session.exec(
        select(Variety).where(Variety.species_id == species_id)
    ).all()
    return any(
        item.id != exclude_id and item.name.strip() == name for item in varieties
    )


def database_error(session, error):
    session.rollback()
    if isinstance(error, IntegrityError):
        st.error(
            "The change conflicts with an existing record or linked data. Refresh and try again."
        )
    else:
        st.error("The database could not save this change. Please try again.")


def show_qr(entity_id, entity_type, width, download=False):
    try:
        path = generate_qr_code(str(entity_id), entity_type)
    except (ValueError, OSError) as error:
        st.warning(f"QR code unavailable: {error}")
        return
    st.image(get_qr_bytes(path), width=width)
    if download:
        qr_bytes = get_qr_bytes(path)
        if qr_bytes:
            st.download_button(
                "Download QR",
                data=qr_bytes,
                file_name=f"Species_{entity_id}_QR.png",
                mime="image/png",
                key=f"dl_s_{entity_id}",
            )


st.set_page_config(page_title="Species & Varieties", page_icon=None, layout="wide")
create_db_and_tables()
render_auth_ui()
if st.session_state.get("toast_message"):
    st.toast(st.session_state.pop("toast_message"))
st.title("Species & Varieties Directory")

with get_session() as session:
    if is_admin():
        with st.expander("Admin Controls: Add New Entries", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Add Species")
                with st.form("add_species_form"):
                    s_name = st.text_input("Species Name")
                    s_desc = st.text_area("Description")
                    s_meta = st.text_area(
                        "Metadata Schema (JSON)",
                        value='[{"name": "pH", "type": "number", "default": 5.5}, {"name": "Light Intensity", "type": "number", "default": 2000}]',
                    )
                    if st.form_submit_button("Save Species"):
                        name = s_name.strip()
                        try:
                            if not name:
                                raise ValueError("Species name cannot be empty.")
                            schema = validate_metadata_schema(s_meta)
                            if species_duplicate(session, name):
                                raise ValueError(
                                    "Species with this name already exists."
                                )
                            item = Species(
                                name=name,
                                description=s_desc,
                                metadata_schema=json.dumps(schema),
                            )
                            session.add(item)
                            session.flush()
                            item.qr_code_path = generate_qr_code(
                                str(item.id), "species"
                            )
                            log_audit(session, "CREATE", "Species", item.id, name)
                            session.commit()
                            st.session_state.toast_message = (
                                f"Species '{name}' added successfully!"
                            )
                            st.rerun()
                        except ValueError as error:
                            session.rollback()
                            st.error(str(error))
                        except SQLAlchemyError as error:
                            database_error(session, error)
                        except OSError:
                            session.rollback()
                            st.error(
                                "Could not save the QR code. Check local file access and try again."
                            )
            with col2:
                st.subheader("Add Variety")
                species_list = session.exec(select(Species)).all()
                if species_list:
                    with st.form("add_variety_form"):
                        v_name = st.text_input("Variety Name")
                        v_species = st.selectbox(
                            "Parent Species",
                            [s.id for s in species_list],
                            format_func=lambda x: next(
                                (s.name for s in species_list if s.id == x), str(x)
                            ),
                        )
                        v_desc = st.text_area("Description")
                        if st.form_submit_button("Save Variety"):
                            name = v_name.strip()
                            try:
                                if not name:
                                    raise ValueError("Variety name cannot be empty.")
                                if variety_duplicate(session, name, v_species):
                                    raise ValueError(
                                        "A variety with this name already exists under this species."
                                    )
                                item = Variety(
                                    name=name, species_id=v_species, description=v_desc
                                )
                                session.add(item)
                                session.flush()
                                item.qr_code_path = generate_qr_code(
                                    str(item.id), "variety"
                                )
                                log_audit(session, "CREATE", "Variety", item.id, name)
                                session.commit()
                                st.session_state.toast_message = (
                                    f"Variety '{name}' added successfully!"
                                )
                                st.rerun()
                            except ValueError as error:
                                session.rollback()
                                st.error(str(error))
                            except SQLAlchemyError as error:
                                database_error(session, error)
                            except OSError:
                                session.rollback()
                                st.error(
                                    "Could not save the QR code. Check local file access and try again."
                                )
                else:
                    st.info("Add a species first.")

    st.write("---")
    st.subheader("Taxonomy Hierarchy")
    species_list = session.exec(select(Species)).all()
    if not species_list:
        st.info("No species found. Switch to Admin mode to add some.")
    for s in species_list:
        with st.expander(f"Species: **{s.name}**", expanded=False):
            col_s1, col_s2 = st.columns([3, 1])
            with col_s1:
                st.write(f"**Description:** {s.description}")
                try:
                    validate_metadata_schema(s.metadata_schema)
                except ValueError as error:
                    st.warning(
                        f"Invalid metadata schema for {s.name}: {error}. An admin can correct it under Edit Species."
                    )
                if is_admin():
                    col_btn1, col_btn2 = st.columns([1, 3])
                    with col_btn1:
                        if st.button("Delete", key=f"del_s_{s.id}"):
                            try:
                                count = len(
                                    session.exec(
                                        select(Variety).where(
                                            Variety.species_id == s.id
                                        )
                                    ).all()
                                )
                                if count:
                                    st.error(
                                        f"Cannot delete. There are {count} varieties linked to this species."
                                    )
                                else:
                                    name, item_id = s.name, s.id
                                    log_audit(
                                        session, "DELETE", "Species", item_id, name
                                    )
                                    session.delete(s)
                                    session.commit()
                                    st.session_state.toast_message = (
                                        f"Species '{name}' deleted."
                                    )
                                    st.rerun()
                            except SQLAlchemyError as error:
                                database_error(session, error)
                    with (
                        col_btn2,
                        st.expander("Edit Species"),
                        st.form(f"edit_species_form_{s.id}"),
                    ):
                        edit_name = st.text_input("Species Name", value=s.name)
                        edit_desc = st.text_area(
                            "Description", value=s.description or ""
                        )
                        edit_meta = st.text_area(
                            "Metadata Schema (JSON)", value=s.metadata_schema
                        )
                        if st.form_submit_button("Save Changes"):
                            name = edit_name.strip()
                            try:
                                if not name:
                                    raise ValueError("Name cannot be empty.")
                                schema = json.dumps(validate_metadata_schema(edit_meta))
                                if species_duplicate(session, name, s.id):
                                    raise ValueError(
                                        "Species with this name already exists."
                                    )
                                old_schema = s.metadata_schema
                                s.name, s.description, s.metadata_schema = (
                                    name,
                                    edit_desc,
                                    schema,
                                )
                                if old_schema != schema:
                                    migrate_racks_metadata(
                                        session, s.id, old_schema, schema
                                    )
                                log_audit(
                                    session,
                                    "UPDATE",
                                    "Species",
                                    s.id,
                                    f"Edited: {name}",
                                )
                                session.commit()
                                st.session_state.toast_message = (
                                    f"Species '{name}' updated successfully!"
                                )
                                st.rerun()
                            except ValueError as error:
                                session.rollback()
                                st.error(str(error))
                            except SQLAlchemyError as error:
                                database_error(session, error)
            with col_s2:
                show_qr(s.id, "species", 120, download=True)
            st.write("---")
            st.markdown(f"##### Varieties of {s.name}")
            varieties = session.exec(
                select(Variety).where(Variety.species_id == s.id)
            ).all()
            if not varieties:
                st.info("No varieties registered under this species.")
            for v in varieties:
                vcol1, vcol2, vcol3, vcol4, vcol5, vcol6 = st.columns(
                    [2, 3, 2, 2, 1, 1]
                )
                vcol1.write(f"**{v.name}**")
                vcol2.write(v.description or "-")
                with vcol3:
                    show_qr(v.id, "variety", 80)
                if vcol4.button("View Racks", key=f"view_r_{v.id}", type="primary"):
                    st.session_state.filter_variety_id = v.id
                    st.switch_page("pages/2_Racks_&_Assets.py")
                if is_admin():
                    if vcol5.button(
                        "Edit", key=f"edit_v_btn_{v.id}", help="Edit Variety"
                    ):
                        st.session_state.editing_variety_id = v.id
                        st.rerun()
                    if vcol6.button(
                        "Delete", key=f"del_v_{v.id}", help="Delete Variety"
                    ):
                        try:
                            count = len(
                                session.exec(
                                    select(Rack).where(Rack.variety_id == v.id)
                                ).all()
                            )
                            if count:
                                st.error(
                                    f"Cannot delete. There are {count} racks linked to this variety."
                                )
                            else:
                                name, item_id = v.name, v.id
                                log_audit(
                                    session,
                                    "DELETE",
                                    "Variety",
                                    item_id,
                                    f"{name} (species: {s.name})",
                                )
                                session.delete(v)
                                session.commit()
                                st.session_state.toast_message = (
                                    f"Variety '{name}' deleted."
                                )
                                st.rerun()
                        except SQLAlchemyError as error:
                            database_error(session, error)
                    if st.session_state.get("editing_variety_id") == v.id:
                        with st.form(f"edit_variety_form_{v.id}"):
                            edit_v_name = st.text_input("Variety Name", value=v.name)
                            edit_v_desc = st.text_area(
                                "Description", value=v.description or ""
                            )
                            ids = [sp.id for sp in species_list]
                            edit_v_species = st.selectbox(
                                "Parent Species",
                                ids,
                                index=ids.index(v.species_id),
                                format_func=lambda x: next(
                                    (sp.name for sp in species_list if sp.id == x),
                                    str(x),
                                ),
                            )
                            c1, c2 = st.columns(2)
                            if c1.form_submit_button("Save Changes"):
                                name = edit_v_name.strip()
                                try:
                                    if not name:
                                        raise ValueError("Name cannot be empty.")
                                    # Legacy duplicates may be edited in place, but cannot be created or moved.
                                    if (
                                        name != v.name.strip()
                                        or edit_v_species != v.species_id
                                    ) and variety_duplicate(
                                        session, name, edit_v_species, v.id
                                    ):
                                        raise ValueError(
                                            "A variety with this name already exists under this species."
                                        )
                                    if edit_v_species != v.species_id:
                                        target = session.get(Species, edit_v_species)
                                        validate_metadata_schema(target.metadata_schema)
                                        for rack in session.exec(
                                            select(Rack).where(Rack.variety_id == v.id)
                                        ).all():
                                            try:
                                                original_metadata = rack.metadata_dict
                                            except ValueError as exc:
                                                raise ValueError(
                                                    f"Repair metadata for rack '{rack.rack_identifier}' before moving this variety."
                                                ) from exc
                                            rack.metadata_json = json.dumps(
                                                reconcile_metadata(
                                                    original_metadata,
                                                    target.metadata_schema,
                                                )
                                            )
                                            session.add(rack)
                                    v.name, v.description, v.species_id = (
                                        name,
                                        edit_v_desc,
                                        edit_v_species,
                                    )
                                    log_audit(
                                        session,
                                        "UPDATE",
                                        "Variety",
                                        v.id,
                                        f"Edited: {name}",
                                    )
                                    session.commit()
                                    st.session_state.editing_variety_id = None
                                    st.session_state.toast_message = (
                                        f"Variety '{name}' updated successfully!"
                                    )
                                    st.rerun()
                                except ValueError as error:
                                    session.rollback()
                                    st.error(str(error))
                                except SQLAlchemyError as error:
                                    database_error(session, error)
                            if c2.form_submit_button("Cancel"):
                                st.session_state.editing_variety_id = None
                                st.rerun()
