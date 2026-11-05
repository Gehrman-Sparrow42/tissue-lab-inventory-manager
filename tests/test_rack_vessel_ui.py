import json
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlmodel import Session, create_engine, select
from streamlit.testing.v1 import AppTest

from modules import database, image_utils, qr_utils
from modules.models import AuditLog, Rack, Species, Variety, Vessel

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def db(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_PASSWORD", "test-private-password")
    monkeypatch.setenv("BASE_URL", "http://localhost:8501")
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'inventory.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(qr_utils, "QR_DIR", tmp_path / "qr")
    monkeypatch.setattr(image_utils, "ROOT", tmp_path)
    monkeypatch.setattr(image_utils, "MANAGED_ROOT", tmp_path)
    database.create_db_and_tables()
    with Session(engine) as session:
        species = Species(
            name="Species",
            metadata_schema='[{"name":"pH","type":"number","default":5.5}]',
        )
        session.add(species)
        session.flush()
        variety = Variety(name="Variety", species_id=species.id)
        session.add(variety)
        session.flush()
        session.add(
            Rack(
                rack_identifier="R1",
                variety_id=variety.id,
                metadata_json='{"pH":"old", "legacy":"kept"}',
            )
        )
        session.commit()
    yield engine
    engine.dispose()


def app(page):
    at = AppTest.from_file(str(ROOT / "main.py"), default_timeout=20)
    at.session_state["is_admin"] = True
    at.session_state["admin_name"] = "Tester"
    at.run().switch_page(f"pages/{page}").run()
    assert not at.exception
    return at


def test_vessel_lifecycle_and_rack_protection(db):
    at = app("3_Vessels.py")
    next(x for x in at.text_input if x.label.startswith("Vessel Identifier")).input(
        "VES1"
    )
    next(x for x in at.button if x.label == "Create Vessel").click().run()
    assert not at.exception
    racks = app("2_Racks_&_Assets.py")
    next(x for x in racks.button if x.label == "Delete Rack").click().run()
    assert any("containing vessels" in x.value for x in racks.error)
    next(x for x in at.text_input if x.key == "edit_vessel_1_name").input("Sample")
    next(x for x in at.button if x.label == "Save Vessel Changes").click().run()
    assert not at.exception
    with Session(db) as session:
        assert session.exec(select(Vessel)).first().name == "Sample"
    next(x for x in at.button if x.label == "Delete Vessel").click().run()
    assert not at.exception
    with Session(db) as session:
        assert not session.exec(select(Vessel)).all()
        logs = session.exec(
            select(AuditLog).where(AuditLog.table_name == "Vessel")
        ).all()
        assert [log.action for log in logs] == ["CREATE", "UPDATE", "DELETE"]
        assert all(log.actor == "Tester" and "VES1" in log.details for log in logs)


def test_metadata_correction_retains_legacy_values(db):
    at = app("2_Racks_&_Assets.py")
    next(x for x in at.button if x.label == "Save Changes").click().run()
    assert any("finite number" in x.value for x in at.error)
    with Session(db) as session:
        assert json.loads(session.get(Rack, 1).metadata_json) == {
            "pH": "old",
            "legacy": "kept",
        }
    next(
        x for x in at.text_input if x.label == "pH" and x.key.startswith("edit_1_")
    ).input("6.2")
    next(x for x in at.button if x.label == "Save Changes").click().run()
    assert not at.exception
    with Session(db) as session:
        assert json.loads(session.get(Rack, 1).metadata_json) == {
            "pH": 6.2,
            "legacy": "kept",
        }


def test_invalid_metadata_does_not_break_other_racks(db):
    with Session(db) as session:
        session.get(Rack, 1).metadata_json = '["invalid"]'
        session.add(Rack(rack_identifier="R2", variety_id=1))
        session.commit()
    at = app("2_Racks_&_Assets.py")
    assert any("Invalid saved metadata" in error.value for error in at.error)
    assert any("R2" in expander.label for expander in at.expander)
    assert len([x for x in at.button if x.label == "Save Changes"]) == 1


@pytest.mark.parametrize("relative_reference", [False, True])
def test_shared_image_is_not_deleted(db, tmp_path, relative_reference):
    image = tmp_path / "shared.jpg"
    image.write_bytes(b"placeholder")
    # Avoid rendering an intentionally minimal image while exercising reference checks.
    with Session(db) as session:
        session.get(Rack, 1).image_url = str(image)
        second_reference = image.name if relative_reference else str(image)
        session.add(
            Rack(rack_identifier="R2", variety_id=1, image_url=second_reference)
        )
        session.commit()
    # A real image is needed by Streamlit rendering.
    from PIL import Image

    Image.new("RGB", (2, 2)).save(image)
    at = app("2_Racks_&_Assets.py")
    next(x for x in at.button if x.key == "del_1").click().run()
    assert not at.exception
    assert image.exists()
    with Session(db) as session:
        assert session.get(Rack, 2).image_url == second_reference


def test_rack_move_rerenders_target_schema_and_preserves_values(db):
    with Session(db) as session:
        species = Species(
            name="Target",
            metadata_schema='[{"name":"Medium","type":"text","default":"MS"}]',
        )
        session.add(species)
        session.flush()
        variety = Variety(name="Target variety", species_id=species.id)
        session.add(variety)
        session.commit()
        target_id = variety.id
    at = app("2_Racks_&_Assets.py")
    next(field for field in at.selectbox if field.key == "edit_variety_1").set_value(
        target_id
    ).run()
    assert not at.exception
    assert any(
        field.label == "Medium" and field.key.startswith("edit_1_")
        for field in at.text_input
    )
    next(button for button in at.button if button.label == "Save Changes").click().run()
    assert not at.exception
    with Session(db) as session:
        rack = session.get(Rack, 1)
        assert rack.variety_id == target_id
        assert rack.metadata_dict == {"pH": "old", "legacy": "kept", "Medium": "MS"}


def test_guest_cannot_mutate_inventory(db):
    for page in ("2_Racks_&_Assets.py", "3_Vessels.py"):
        at = (
            AppTest.from_file(str(ROOT / "main.py"))
            .run()
            .switch_page(f"pages/{page}")
            .run()
        )
        assert not at.exception
        assert not any(
            button.label
            in {"Create Rack", "Delete Rack", "Save Changes", "Create Vessel"}
            for button in at.button
        )


def test_raw_metadata_repair_preserves_original_audit(db):
    original = "malformed legacy payload"
    with Session(db) as session:
        session.get(Rack, 1).metadata_json = original
        session.commit()
    at = app("2_Racks_&_Assets.py")
    next(field for field in at.text_area if field.key == "repair_raw_1").set_value("[]")
    next(
        button for button in at.button if button.label == "Repair Metadata"
    ).click().run()
    assert not at.exception
    assert any("JSON object" in error.value for error in at.error)
    next(field for field in at.text_area if field.key == "repair_raw_1").set_value(
        '{"pH":5.8,"recovered":"kept"}'
    )
    next(
        button for button in at.button if button.label == "Repair Metadata"
    ).click().run()
    assert not at.exception
    with Session(db) as session:
        assert session.get(Rack, 1).metadata_dict == {"pH": 5.8, "recovered": "kept"}
        event = session.exec(select(AuditLog).where(AuditLog.action == "REPAIR")).one()
        assert json.loads(event.details)["original_metadata"] == original
        assert event.actor == "Tester"
