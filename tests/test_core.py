import sqlite3

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, create_engine, select
from streamlit.testing.v1 import AppTest

from modules import database
from modules.models import AuditLog, Rack, Species, Variety, Vessel
from modules.validation import (
    migrate_racks_metadata,
    reconcile_metadata,
    validate_metadata_schema,
    validate_metadata_values,
)


@pytest.fixture
def db_engine(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + (tmp_path / "inventory.db").as_posix())

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "IS_POSTGRES", False)
    database.create_db_and_tables()
    yield engine
    engine.dispose()


def hierarchy(session, schema="[]"):
    species = Species(name="Species A", metadata_schema=schema)
    session.add(species)
    session.flush()
    variety = Variety(name="Variety A", species_id=species.id)
    session.add(variety)
    session.flush()
    rack = Rack(
        rack_identifier="R&1",
        variety_id=variety.id,
        metadata_json='{"old": 4, "pH": "unknown"}',
    )
    session.add(rack)
    session.flush()
    return species, variety, rack


@pytest.mark.parametrize(
    "schema",
    [
        "{}",
        "not json",
        '[{"name": 42}]',
        '[{"name":"   "}]',
        '[{"name":"pH"},{"name":" pH "}]',
        '[{"name":"pH","type":"number","default":"five"}]',
        '[{"name":"pH","type":"number","default":true}]',
        '[{"name":"pH","type":"number","default":"NaN"}]',
    ],
)
def test_invalid_schema_is_actionable(schema):
    with pytest.raises(ValueError):
        validate_metadata_schema(schema)


def test_metadata_preserves_removed_and_incompatible_values():
    schema = (
        '[{"name":"pH","type":"number","default":5.5},{"name":"new","default":"x"}]'
    )
    values = reconcile_metadata({"old": 4, "pH": "unknown"}, schema)
    assert values == {"old": 4, "pH": "unknown", "new": "x"}
    with pytest.raises(ValueError, match="pH"):
        validate_metadata_values(values, schema)
    values["pH"] = "6.2"
    assert validate_metadata_values(values, schema) == {"old": 4, "pH": 6.2, "new": "x"}


def test_atomic_migration_and_audit(db_engine):
    with Session(db_engine) as session:
        species, _, rack = hierarchy(session)
        session.commit()
        species_id, rack_id = species.id, rack.id
        new_schema = '[{"name":"new","type":"number","default":7}]'
        species.metadata_schema = new_schema
        migrate_racks_metadata(session, species.id, "invalid old schema", new_schema)
        database.log_audit(
            session, "UPDATE", "Species", species.id, "Schema", actor="operator"
        )
        session.rollback()
    with Session(db_engine) as session:
        assert session.get(Species, species_id).metadata_schema == "[]"
        assert session.get(Rack, rack_id).metadata_dict == {"old": 4, "pH": "unknown"}
        assert not session.exec(select(AuditLog)).all()
        migrate_racks_metadata(session, species_id, "[]", new_schema)
        database.log_audit(
            session, "UPDATE", "Species", species_id, "Schema", actor="operator"
        )
        session.commit()
    with Session(db_engine) as session:
        assert session.get(Rack, rack_id).metadata_dict == {
            "old": 4,
            "pH": "unknown",
            "new": 7,
        }
        assert session.exec(select(AuditLog)).one().actor == "operator"


def test_foreign_keys_and_duplicate_variety(db_engine):
    with Session(db_engine) as session:
        _, variety, rack = hierarchy(session)
        session.add(Vessel(vessel_identifier="V1", rack_id=rack.id))
        session.commit()
        session.add(Variety(name=variety.name, species_id=variety.species_id))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.delete(rack)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_legacy_columns_and_duplicate_names_preserved(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + (tmp_path / "old.db").as_posix())
    # Create an authentic old schema, omitting columns added by this update.
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE species (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL)")
        )
        connection.execute(
            text(
                "CREATE TABLE variety (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, species_id INTEGER NOT NULL)"
            )
        )
        connection.execute(text("CREATE TABLE rack (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE auditlog (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO species VALUES (1, 'A')"))
        connection.execute(
            text("INSERT INTO variety VALUES (1, 'same', 1), (2, 'same', 1)")
        )
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "IS_POSTGRES", False)
    database.create_db_and_tables()
    database.create_db_and_tables()
    with engine.begin() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM variety")).scalar() == 2
        assert "actor" in {
            r[1] for r in connection.execute(text("PRAGMA table_info(auditlog)"))
        }
        assert {"name", "description"} <= {
            r[1] for r in connection.execute(text("PRAGMA table_info(rack)"))
        }
        connection.execute(text("UPDATE variety SET name='repaired' WHERE id=2"))
    database.create_db_and_tables()
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(text("INSERT INTO variety VALUES (3, 'same', 1)"))
    engine.dispose()


def test_snapshot_contains_current_database(db_engine):
    with Session(db_engine) as session:
        hierarchy(session)
        session.commit()
    payload = database.export_sqlite_backup()
    with sqlite3.connect(":memory:") as restored:
        restored.deserialize(payload)
        assert restored.execute("SELECT rack_identifier FROM rack").fetchone() == (
            "R&1",
        )
        assert restored.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_malformed_legacy_metadata_is_never_silently_replaced():
    for raw in ("not json", "[]", "null"):
        with pytest.raises(ValueError):
            _ = Rack(
                rack_identifier="bad", variety_id=1, metadata_json=raw
            ).metadata_dict


def test_auth_has_no_shutdown_and_disables_default_password(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "admin")
    app = AppTest.from_string(
        "from modules.auth import render_auth_ui\nrender_auth_ui()"
    ).run()
    assert not app.exception
    assert not app.button
    assert any("disabled" in message.value for message in app.info)


def test_auth_unicode_login_and_logout(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "private-şifre-123")
    app = AppTest.from_string(
        "from modules.auth import render_auth_ui\nrender_auth_ui()"
    ).run()
    app.text_input[0].set_value("Researcher")
    app.text_input[1].set_value("private-şifre-123")
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state.is_admin
    assert app.session_state.admin_name == "Researcher"
    assert "Stop Server" not in [button.label for button in app.button]
    next(button for button in app.button if button.label == "Logout").click().run()
    assert not app.session_state.is_admin


@pytest.mark.parametrize(
    "kind,identifier",
    [
        ("species", "1"),
        ("variety", "1"),
        ("rack", "R&1"),
        ("vessel", "V#1"),
        ("unknown", "1"),
        ("species", "abc"),
        ("species", "999999999999999999999999999999"),
        ("rack", ""),
        ("rack", "missing"),
    ],
)
def test_dashboard_scan_routes(db_engine, tmp_path, monkeypatch, kind, identifier):
    from pathlib import Path

    from modules import qr_utils

    monkeypatch.setattr(qr_utils, "QR_DIR", tmp_path / "qr")
    with Session(db_engine) as session:
        _, _, rack = hierarchy(session)
        session.add(Vessel(vessel_identifier="V#1", rack_id=rack.id))
        session.commit()
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "main.py"))
    app.query_params.update({"type": kind, "id": identifier})
    app.run()
    assert not app.exception
    if kind == "unknown" or identifier in {
        "abc",
        "",
        "missing",
        "999999999999999999999999999999",
    }:
        assert app.error
    else:
        assert not app.error
        assert app.subheader


def test_dashboard_bad_qr_config_does_not_block_exports(db_engine, monkeypatch):
    from pathlib import Path

    monkeypatch.setenv("ADMIN_PASSWORD", "test-private-password")
    monkeypatch.setenv("BASE_URL", "not a URL")
    with Session(db_engine) as session:
        hierarchy(session)
        session.commit()
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "main.py"))
    app.session_state.is_admin = True
    app.run()
    assert not app.exception
    assert any(
        "Printable labels unavailable" in warning.value for warning in app.warning
    )


def test_sample_cli_creates_audited_data_and_refuses_existing_file(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    target = tmp_path / "sample.db"
    result = subprocess.run(
        [sys.executable, str(root / "populate.py"), str(target)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT COUNT(*) FROM auditlog").fetchone() == (3,)
    original = target.read_bytes()
    result = subprocess.run(
        [sys.executable, str(root / "populate.py"), str(target)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert target.read_bytes() == original


def test_bare_database_filename_initializes_without_directory_error(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, DB_PATH="inventory.db", PYTHONPATH=str(root))
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from modules.database import SQLITE_PATH; print(SQLITE_PATH)",
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(root / "inventory.db")


def test_schema_migration_identifies_malformed_rack(db_engine):
    with Session(db_engine) as session:
        species, _, rack = hierarchy(session)
        rack.metadata_json = "malformed legacy payload"
        session.commit()
        with pytest.raises(ValueError, match="R&1"):
            migrate_racks_metadata(session, species.id, "[]", "[]")
        session.rollback()
        assert rack.metadata_json == "malformed legacy payload"


def test_workspace_search_and_record_filter(db_engine):
    from pathlib import Path

    with Session(db_engine) as session:
        _, _, rack = hierarchy(session)
        session.add(Vessel(vessel_identifier="Vessel-1", rack_id=rack.id))
        session.commit()
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "main.py")).run()
    app.text_input(key="workspace_search").set_value("R&1")
    app.selectbox(key="workspace_type").set_value("Racks").run()
    assert not app.exception
    table = next(
        item.value for item in app.markdown if 'class="inventory-table"' in item.value
    )
    assert table.count("<tr>") == 2
    assert "R&amp;1" in table
    assert "type=rack&amp;id=R%261" in table
    assert 'target="_blank"' in table
    app.text_input(key="workspace_search").set_value("does-not-exist").run()
    assert any("Try another search" in item.value for item in app.info)


def test_workspace_escapes_record_names(db_engine):
    from pathlib import Path

    with Session(db_engine) as session:
        session.add(Species(name="<img src=x onerror=alert(1)>"))
        session.commit()
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "main.py")).run()
    assert not app.exception
    table = next(
        item.value for item in app.markdown if 'class="inventory-table"' in item.value
    )
    assert "<img src=x" not in table
    assert "&lt;img src=x" in table


def test_workspace_navigation_preserves_admin_session(db_engine, monkeypatch):
    from pathlib import Path

    monkeypatch.setenv("ADMIN_PASSWORD", "test-private-password")
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "main.py"))
    app.session_state.is_admin = True
    app.run()
    next(
        button for button in app.button if button.label == "Browse racks"
    ).click().run()
    assert not app.exception
    assert app.title[0].value == "Racks & assets"
    assert app.session_state.is_admin


def test_vessel_status_filter_scopes_responsive_records(db_engine):
    from pathlib import Path

    with Session(db_engine) as session:
        _, _, rack = hierarchy(session)
        session.add_all(
            [
                Vessel(
                    vessel_identifier="CLEAN-1",
                    rack_id=rack.id,
                    contamination_status="Clean",
                ),
                Vessel(
                    vessel_identifier="SUSPECT-1",
                    rack_id=rack.id,
                    contamination_status="Suspected",
                ),
            ]
        )
        session.commit()
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "main.py")).run()
    app.switch_page("pages/3_Vessels.py").run()
    app.selectbox(key="vessel_status_filter").set_value("Suspected").run()
    assert not app.exception
    table = next(
        item.value for item in app.markdown if 'class="inventory-table"' in item.value
    )
    assert "SUSPECT-1" in table
    assert "CLEAN-1" not in table
    assert "status-warning" in table
