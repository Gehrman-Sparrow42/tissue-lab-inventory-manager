import hmac
import os
import sqlite3
import time

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from modules.database import IS_POSTGRES, SQLITE_PATH, export_sqlite_backup

_UNSAFE_PASSWORDS = {"", "admin", "change_this_admin_password_in_production"}


def _configured_password():
    password = os.getenv("ADMIN_PASSWORD", "")
    return password if password.strip().lower() not in _UNSAFE_PASSWORDS else None


def init_auth():
    st.session_state.setdefault("is_admin", False)


def is_admin():
    return bool(_configured_password() and st.session_state.get("is_admin", False))


def render_auth_ui():
    init_auth()
    with st.sidebar:
        if is_admin():
            st.markdown(
                '<div class="sidebar-access"><strong>Editing enabled</strong>Admin access</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                f"Operator label — {st.session_state.get('admin_name', 'Admin')}"
            )
            if st.button("Logout"):
                st.session_state.is_admin = False
                st.session_state.pop("admin_name", None)
                st.session_state.pop("database_backup", None)
                st.rerun()
            if IS_POSTGRES:
                st.caption("Use PostgreSQL backup tools to export this database.")
            else:
                st.caption(f"Database — {SQLITE_PATH.name}")
                if st.button("Prepare Database Backup"):
                    try:
                        st.session_state.database_backup = export_sqlite_backup()
                    except (SQLAlchemyError, OSError, sqlite3.Error):
                        st.error(
                            "Backup could not be prepared. Check database access and try again."
                        )
                if "database_backup" in st.session_state:
                    st.download_button(
                        "Export Database",
                        st.session_state.database_backup,
                        "inventory_backup.db",
                        "application/octet-stream",
                    )
                    st.caption(
                        "Snapshot from the last preparation. Prepare again to include newer changes."
                    )
        else:
            password = _configured_password()
            if password is None:
                st.info("Admin editing is disabled.")
                return
            with st.expander("Admin Login", expanded=False):
                operator = st.text_input(
                    "Operator label",
                    value="Admin",
                    help="Recorded in audit events. This is a self-reported label for the shared admin login.",
                )
                entered = st.text_input("Password", type="password")
                if st.button("Login"):
                    now = time.monotonic()
                    if now < st.session_state.get("login_locked_until", 0):
                        st.error(
                            "Too many attempts. Wait one minute before trying again."
                        )
                    elif not operator.strip():
                        st.error("Enter an operator label for the audit log.")
                    elif hmac.compare_digest(
                        entered.encode("utf-8"), password.encode("utf-8")
                    ):
                        st.session_state.is_admin = True
                        st.session_state.admin_name = operator.strip()
                        st.session_state.login_attempts = 0
                        st.rerun()
                    else:
                        attempts = st.session_state.get("login_attempts", 0) + 1
                        st.session_state.login_attempts = attempts
                        if attempts >= 5:
                            st.session_state.login_locked_until = now + 60
                            st.session_state.login_attempts = 0
                        st.error("Invalid password.")
