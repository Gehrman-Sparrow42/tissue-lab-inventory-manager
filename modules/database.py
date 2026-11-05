import os
import sqlite3
from pathlib import Path
from threading import RLock

from dotenv import load_dotenv
from sqlalchemy import event, inspect, text
from sqlmodel import Session, SQLModel, create_engine

load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = "data/inventory_v2.db"
# Keep older installations on their existing file when there is no explicit choice.
if (
    not (PROJECT_ROOT / DEFAULT_DB_PATH).exists()
    and (PROJECT_ROOT / "data/inventory.db").exists()
):
    DEFAULT_DB_PATH = "data/inventory.db"
cloud_database = (
    os.getenv("DATABASE_URL") if os.getenv("CLOUD_DEPLOYMENT") == "1" else None
)
DB_PATH = os.getenv("DB_PATH") or cloud_database or DEFAULT_DB_PATH
IS_POSTGRES = DB_PATH.startswith(("postgresql://", "postgres://"))
if IS_POSTGRES:
    database_url = DB_PATH.replace("postgres://", "postgresql://", 1)
    SQLITE_PATH = None
else:
    SQLITE_PATH = Path(DB_PATH).expanduser()
    if not SQLITE_PATH.is_absolute():
        SQLITE_PATH = PROJECT_ROOT / SQLITE_PATH
    SQLITE_PATH = SQLITE_PATH.resolve()
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    database_url = "sqlite:///" + SQLITE_PATH.as_posix()

engine = create_engine(database_url, echo=False, pool_pre_ping=True)
_initialization_lock = RLock()


if not IS_POSTGRES:

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")


def create_db_and_tables():
    """Initialize new databases and add compatible columns without dropping data."""
    from modules import models  # noqa: F401 — register all tables

    with _initialization_lock, engine.begin() as connection:
        if IS_POSTGRES:
            # New instances may start together after Vercel scales out.
            connection.execute(text("SELECT pg_advisory_xact_lock(1230762035)"))
        SQLModel.metadata.create_all(connection)
        for table, additions in (
            ("rack", {"name": "VARCHAR", "description": "VARCHAR"}),
            ("auditlog", {"actor": "VARCHAR"}),
        ):
            existing = {
                column["name"] for column in inspect(connection).get_columns(table)
            }
            for name, sql_type in additions.items():
                if name not in existing:
                    connection.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
                    )

        duplicate = connection.execute(
            text(
                "SELECT 1 FROM variety GROUP BY species_id, name HAVING COUNT(*) > 1 LIMIT 1"
            )
        ).first()
        if not duplicate:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_variety_species_name ON variety (species_id, name)"
                )
            )
        # Triggers keep pre-existing duplicate rows intact while preventing new
        # collisions. Once names are repaired the unique index is installed.
        if not IS_POSTGRES:
            connection.execute(
                text("""
                CREATE TRIGGER IF NOT EXISTS variety_unique_insert
                BEFORE INSERT ON variety
                WHEN EXISTS (SELECT 1 FROM variety
                             WHERE species_id = NEW.species_id AND name = NEW.name)
                BEGIN SELECT RAISE(ABORT, 'Variety name already exists in this species'); END
            """)
            )
            connection.execute(
                text("""
                CREATE TRIGGER IF NOT EXISTS variety_unique_update
                BEFORE UPDATE OF name, species_id ON variety
                WHEN (NEW.name != OLD.name OR NEW.species_id != OLD.species_id)
                     AND EXISTS (SELECT 1 FROM variety WHERE species_id = NEW.species_id
                                 AND name = NEW.name AND id != OLD.id)
                BEGIN SELECT RAISE(ABORT, 'Variety name already exists in this species'); END
            """)
            )
        elif duplicate:
            # Serialize checks for a particular name even for legacy databases
            # that cannot yet accept the composite unique index.
            connection.execute(
                text("""
                CREATE OR REPLACE FUNCTION enforce_variety_name() RETURNS trigger AS $$
                BEGIN
                    IF TG_OP = 'UPDATE' THEN
                        IF NEW.name = OLD.name AND NEW.species_id = OLD.species_id THEN
                            RETURN NEW;
                        END IF;
                    END IF;
                    PERFORM pg_advisory_xact_lock(
                        hashtextextended(NEW.species_id::text || ':' || NEW.name, 0));
                    IF EXISTS (SELECT 1 FROM variety WHERE species_id = NEW.species_id
                               AND name = NEW.name AND id IS DISTINCT FROM NEW.id) THEN
                        RAISE unique_violation USING MESSAGE = 'Variety name already exists in this species';
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
            """)
            )
            if not connection.execute(
                text(
                    "SELECT 1 FROM pg_trigger WHERE tgname = 'variety_name_guard' "
                    "AND tgrelid = 'variety'::regclass AND NOT tgisinternal"
                )
            ).first():
                connection.execute(
                    text("""
                    CREATE TRIGGER variety_name_guard BEFORE INSERT OR UPDATE ON variety
                    FOR EACH ROW EXECUTE FUNCTION enforce_variety_name()
                """)
                )


def get_session():
    """Callers own the transaction and close it using a with block."""
    return Session(engine)


def log_audit(session, action, table_name, record_id, details="", actor=None):
    """Stage an audit event in the same transaction as the changed record."""
    from modules.models import AuditLog

    if actor is None:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        if get_script_run_ctx(suppress_warning=True) is not None:
            import streamlit as st

            actor = st.session_state.get("admin_name", "Admin")
    session.add(
        AuditLog(
            action=action,
            table_name=table_name,
            record_id=record_id,
            details=details,
            actor=actor,
        )
    )


def export_sqlite_backup():
    """Return a transaction-consistent snapshot of the active SQLite database."""
    if IS_POSTGRES:
        raise ValueError("Use PostgreSQL backup tools for this database.")
    with sqlite3.connect(":memory:") as snapshot:
        raw_connection = engine.raw_connection()
        try:
            raw_connection.driver_connection.backup(snapshot)
            return snapshot.serialize()
        finally:
            raw_connection.close()
