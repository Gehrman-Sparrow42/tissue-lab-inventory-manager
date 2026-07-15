from sqlalchemy.orm import clear_mappers
clear_mappers()
from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime, timezone
import json

def get_utc_now():
    return datetime.now(timezone.utc)

class AuditLog(SQLModel, table=True):
    __table_args__ = {'extend_existing': True}
    id: Optional[int] = Field(default=None, primary_key=True)
    action: str
    table_name: str
    record_id: Optional[int] = None
    timestamp: datetime = Field(default_factory=get_utc_now)
    details: Optional[str] = None

class Species(SQLModel, table=True):
    __table_args__ = {'extend_existing': True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    description: Optional[str] = None
    metadata_schema: str = Field(default='[{"name": "pH", "type": "number", "default": 5.5}, {"name": "Light Intensity", "type": "number", "default": 2000}]')
    qr_code_path: Optional[str] = None
    created_at: datetime = Field(default_factory=get_utc_now)

class Variety(SQLModel, table=True):
    __table_args__ = {'extend_existing': True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    species_id: int = Field(foreign_key="species.id")
    description: Optional[str] = None
    qr_code_path: Optional[str] = None
    created_at: datetime = Field(default_factory=get_utc_now)

class Rack(SQLModel, table=True):
    __table_args__ = {'extend_existing': True}
    id: Optional[int] = Field(default=None, primary_key=True)
    rack_identifier: str = Field(index=True, unique=True)
    variety_id: int = Field(foreign_key="variety.id")
    name: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    
    qr_code_path: Optional[str] = None
    image_url: Optional[str] = None
    metadata_json: str = Field(default="{}")
    
    created_at: datetime = Field(default_factory=get_utc_now)

    @property
    def metadata_dict(self) -> dict:
        try:
            return json.loads(self.metadata_json)
        except:
            return {}
