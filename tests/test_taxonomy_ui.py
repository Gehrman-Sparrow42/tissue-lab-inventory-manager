import json
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from streamlit.testing.v1 import AppTest

from modules import database, qr_utils
from modules.models import AuditLog, Rack, Species, Variety

PAGE = str(Path(__file__).resolve().parents[1] / "pages" / "1_Species_&_Varieties.py")


@pytest.fixture
def db(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_PASSWORD", "test-strong-password")
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'taxonomy.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(database, "engine", engine)
    SQLModel.metadata.create_all(engine)
    # QR rendering should never depend on an external service in these UI tests.
    from PIL import Image

    image = tmp_path / "qr.png"
    Image.new("RGB", (2, 2), "white").save(image)
    monkeypatch.setattr(qr_utils, "generate_qr_code", lambda *_: str(image))
    yield engine
    engine.dispose()


def app():
    at = AppTest.from_file(PAGE, default_timeout=20)
    at.session_state["is_admin"] = True
    at.run()
    assert not at.exception
    return at


def test_invalid_schema_and_duplicate_species_rename(db):
    with Session(db) as session:
        session.add_all([Species(name="First"), Species(name="Second")])
        session.commit()
    at = app()
    next(
        x for x in at.text_input if x.label == "Species Name" and x.value == ""
    ).set_value("New")
    next(
        x
        for x in at.text_area
        if x.label == "Metadata Schema (JSON)" and "pH" in x.value
    ).set_value('{"bad": true}')
    next(x for x in at.button if x.label == "Save Species").click().run()
    assert not at.exception
    assert at.error
    next(
        x for x in at.text_input if x.label == "Species Name" and x.value == "First"
    ).set_value(" Second ")
    # The first edit form belongs to First.
    next(x for x in at.button if x.label == "Save Changes").click().run()
    assert not at.exception
    assert any("already exists" in x.value for x in at.error)
    with Session(db) as session:
        assert sorted(x.name for x in session.exec(select(Species)).all()) == [
            "First",
            "Second",
        ]


def test_variety_reparent_preserves_metadata_and_audits(db):
    with Session(db) as session:
        first = Species(name="First", metadata_schema="[]")
        second = Species(
            name="Second",
            metadata_schema='[{"name":"new", "type":"text", "default":"value"}]',
        )
        session.add_all([first, second])
        session.flush()
        variety = Variety(name="Variety", species_id=first.id)
        session.add(variety)
        session.flush()
        session.add(
            Rack(
                rack_identifier="R1",
                variety_id=variety.id,
                metadata_json='{"old":"kept"}',
            )
        )
        session.commit()
        second_id = second.id
    at = app()
    next(x for x in at.button if x.key == "edit_v_btn_1").click().run()
    [x for x in at.selectbox if x.label == "Parent Species"][-1].set_value(second_id)
    [x for x in at.button if x.label == "Save Changes"][1].click().run()
    assert not at.exception
    with Session(db) as session:
        assert session.get(Variety, 1).species_id == second_id
        assert json.loads(session.get(Rack, 1).metadata_json) == {
            "old": "kept",
            "new": "value",
        }
        assert (
            session.exec(select(AuditLog).where(AuditLog.action == "UPDATE")).first()
            is not None
        )
