import os
from sqlmodel import create_engine, SQLModel, Session
from dotenv import load_dotenv

load_dotenv(override=True)

DB_PATH = os.getenv("DB_PATH", "data/inventory_v2.db")

if DB_PATH.startswith("postgresql://") or DB_PATH.startswith("postgres://"):
    # Convert postgres:// to postgresql:// as required by newer SQLAlchemy versions
    sqlite_url = DB_PATH.replace("postgres://", "postgresql://")
else:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    sqlite_url = f"sqlite:///{DB_PATH}"

engine = create_engine(sqlite_url, echo=False)

def create_db_and_tables():
    from modules.models import Species, Variety, Rack, AuditLog
    SQLModel.metadata.create_all(engine)
    
    # SQLite schema migration to add name and description columns to rack if missing
    from sqlalchemy import text
    with Session(engine) as session:
        for col in ["name", "description"]:
            try:
                session.exec(text(f"ALTER TABLE rack ADD COLUMN {col} VARCHAR"))
                session.commit()
            except Exception:
                session.rollback()

def get_session():
    return Session(engine)

def log_audit(session: Session, action: str, table_name: str, record_id: int, details: str = ""):
    from modules.models import AuditLog
    log = AuditLog(action=action, table_name=table_name, record_id=record_id, details=details)
    session.add(log)
    session.commit()
