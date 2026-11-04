"""Create example data only in a new, explicitly named SQLite database."""

import argparse
import json
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from modules.models import AuditLog, Rack, Species, Variety


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "database",
        help="Path to a new SQLite database; existing files are never overwritten",
    )
    args = parser.parse_args()
    path = Path(args.database).resolve()
    if path.exists():
        parser.error("The target already exists; choose a new scratch database path.")
    if not path.parent.is_dir():
        parser.error("The target directory must already exist.")
    # Reserve the name exclusively to avoid overwriting an existing database.
    try:
        with path.open("xb"):
            pass
    except FileExistsError:
        parser.error("The target already exists; choose a new scratch database path.")
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        species = Species(name="Example species", description="Example data")
        session.add(species)
        session.flush()
        variety = Variety(name="Example variety", species_id=species.id)
        session.add(variety)
        session.flush()
        rack = Rack(
            rack_identifier="EXAMPLE-001",
            variety_id=variety.id,
            name="Example rack",
            metadata_json=json.dumps({"pH": 5.8}),
        )
        session.add(rack)
        session.flush()
        for kind, record in (
            ("Species", species),
            ("Variety", variety),
            ("Rack", rack),
        ):
            session.add(
                AuditLog(
                    action="CREATE",
                    table_name=kind,
                    record_id=record.id,
                    details="Illustrative sample record",
                    actor="Sample data generator",
                )
            )
        session.commit()
    engine.dispose()
    print(f"Created example database: {path}")


if __name__ == "__main__":
    main()
