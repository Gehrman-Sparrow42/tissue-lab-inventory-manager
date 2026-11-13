"""Regression tests for cached schema initialization and persistent DB-backed login lockout."""

from pathlib import Path

import pytest
from sqlalchemy import event
from sqlmodel import Session, create_engine
from streamlit.testing.v1 import AppTest

from modules import auth, database
from modules.models import AuthState

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def isolated_engine(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite:///" + (tmp_path / "isolated_inventory.db").as_posix(),
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "IS_POSTGRES", False)
    auth._MEMORY_LOCKOUTS.clear()
    yield engine
    auth._MEMORY_LOCKOUTS.clear()
    engine.dispose()


def test_create_db_and_tables_cached_across_streamlit_reruns_and_pages(
    isolated_engine, monkeypatch
):
    call_count = 0
    real_runner = database._run_create_db_and_tables

    def counting_runner():
        nonlocal call_count
        call_count += 1
        return real_runner()

    monkeypatch.setattr(database, "_run_create_db_and_tables", counting_runner)

    at = AppTest.from_file(str(ROOT / "main.py"), default_timeout=20)
    at.run()
    assert not at.exception
    assert call_count == 1

    # Rerunning the same page and switching across all multipage entrypoints must not re-run DDL
    at.run()
    at.switch_page("pages/1_Species_&_Varieties.py").run()
    at.switch_page("pages/2_Racks_&_Assets.py").run()
    at.switch_page("pages/3_Vessels.py").run()
    assert not at.exception
    assert call_count == 1


def test_login_lockout_persists_across_new_sessions_and_recovers_after_expiry(
    isolated_engine, monkeypatch
):
    database.create_db_and_tables()
    monkeypatch.setenv("ADMIN_PASSWORD", "secret-lab-password")

    now = [1000.0]
    monkeypatch.setattr(auth.time, "time", lambda: now[0])

    # Session 1 submits 5 invalid login attempts
    session1 = AppTest.from_string(
        "from modules.auth import render_auth_ui\nrender_auth_ui()"
    ).run()
    for _ in range(5):
        session1.text_input[0].set_value("Attacker")
        session1.text_input[1].set_value("wrong-password")
        session1.button[0].click().run()
        assert not session1.exception
        assert any("Invalid password." in err.value for err in session1.error)

    with Session(isolated_engine) as session:
        row = session.get(AuthState, auth.LOCKOUT_SCOPE)
        assert row is not None
        assert row.locked_until == pytest.approx(1060.0)
        assert row.failed_attempts == 0

    # Session 2 starts with clean session_state (new tab) and even submits the correct password:
    # persistent DB-backed lockout must still reject it.
    now[0] = 1030.0
    session2 = AppTest.from_string(
        "from modules.auth import render_auth_ui\nrender_auth_ui()"
    ).run()
    session2.text_input[0].set_value("Admin")
    session2.text_input[1].set_value("secret-lab-password")
    session2.button[0].click().run()
    assert not session2.exception
    assert not session2.session_state.is_admin
    assert any("Too many attempts" in err.value for err in session2.error)

    # Once lockout expires, valid credentials succeed and reset DB state
    now[0] = 1061.0
    session3 = AppTest.from_string(
        "from modules.auth import render_auth_ui\nrender_auth_ui()"
    ).run()
    session3.text_input[0].set_value("Admin")
    session3.text_input[1].set_value("secret-lab-password")
    session3.button[0].click().run()
    assert not session3.exception
    assert session3.session_state.is_admin is True

    with Session(isolated_engine) as session:
        row = session.get(AuthState, auth.LOCKOUT_SCOPE)
        assert row is not None
        assert row.failed_attempts == 0
        assert row.locked_until == 0.0
