import hmac
import os
import sqlite3
import threading
import time

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

import modules.database as db_module
from modules.models import AuthState
from modules.ui import download_file

_UNSAFE_PASSWORDS = {"", "admin", "change_this_admin_password_in_production"}
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 60.0
LOCKOUT_SCOPE = "admin_login"
_LOCKOUT_MUTEX = threading.RLock()
_MEMORY_LOCKOUTS: dict[str, tuple[int, float]] = {}


def _memory_key(scope: str = LOCKOUT_SCOPE) -> str:
    return f"{db_module.engine.url}|{scope}"


def _is_locked_out(now: float, scope: str = LOCKOUT_SCOPE) -> bool:
    with _LOCKOUT_MUTEX:
        try:
            with db_module.get_session() as session:
                row = session.get(AuthState, scope)
                if row is not None:
                    return now < row.locked_until
        except SQLAlchemyError:
            pass
        _, locked_until = _MEMORY_LOCKOUTS.get(_memory_key(scope), (0, 0.0))
        return now < locked_until


def _record_failed_attempt(now: float, scope: str = LOCKOUT_SCOPE) -> tuple[int, float]:
    with _LOCKOUT_MUTEX:
        try:
            with db_module._initialization_lock:
                AuthState.__table__.create(bind=db_module.engine, checkfirst=True)
            with db_module.get_session() as session:
                row = session.get(AuthState, scope)
                if row is None:
                    row = AuthState(scope=scope, failed_attempts=0, locked_until=0.0)
                    session.add(row)
                elif row.locked_until and now >= row.locked_until:
                    row.locked_until = 0.0
                row.failed_attempts += 1
                if row.failed_attempts >= MAX_LOGIN_ATTEMPTS:
                    row.locked_until = now + LOCKOUT_SECONDS
                    row.failed_attempts = 0
                session.commit()
                _MEMORY_LOCKOUTS[_memory_key(scope)] = (row.failed_attempts, row.locked_until)
                return row.failed_attempts, row.locked_until
        except SQLAlchemyError:
            key = _memory_key(scope)
            attempts, locked_until = _MEMORY_LOCKOUTS.get(key, (0, 0.0))
            if locked_until and now >= locked_until:
                locked_until = 0.0
            attempts += 1
            if attempts >= MAX_LOGIN_ATTEMPTS:
                locked_until = now + LOCKOUT_SECONDS
                attempts = 0
            _MEMORY_LOCKOUTS[key] = (attempts, locked_until)
            return attempts, locked_until


def _clear_lockout(scope: str = LOCKOUT_SCOPE) -> None:
    with _LOCKOUT_MUTEX:
        _MEMORY_LOCKOUTS.pop(_memory_key(scope), None)
        try:
            with db_module.get_session() as session:
                row = session.get(AuthState, scope)
                if row is not None and (row.failed_attempts or row.locked_until):
                    row.failed_attempts = 0
                    row.locked_until = 0.0
                    session.commit()
        except SQLAlchemyError:
            pass


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
            if db_module.IS_POSTGRES:
                st.caption("Use PostgreSQL backup tools to export this database.")
            else:
                st.caption(f"Database — {db_module.SQLITE_PATH.name}")
                if st.button("Prepare Database Backup"):
                    try:
                        st.session_state.database_backup = db_module.export_sqlite_backup()
                    except (SQLAlchemyError, OSError, sqlite3.Error):
                        st.error(
                            "Backup could not be prepared. Check database access and try again."
                        )
                if "database_backup" in st.session_state:
                    download_file(
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
                    now = time.time()
                    if _is_locked_out(now):
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
                        _clear_lockout()
                        st.rerun()
                    else:
                        _record_failed_attempt(now)
                        st.error("Invalid password.")
