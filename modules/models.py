# Validation failures use ValueError consistently across stored and submitted data.
# ruff: noqa: TRY004
import json
from datetime import date, datetime, timezone

from sqlmodel import Field, SQLModel


def get_utc_now():
    return datetime.now(timezone.utc)


class AuditLog(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: int | None = Field(default=None, primary_key=True)
    action: str
    table_name: str
    record_id: int | None = None
    timestamp: datetime = Field(default_factory=get_utc_now)
    details: str | None = None
    actor: str | None = None


class Species(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    description: str | None = None
    metadata_schema: str = Field(
        default='[{"name": "pH", "type": "number", "default": 5.5}, {"name": "Light Intensity", "type": "number", "default": 2000}]'
    )
    qr_code_path: str | None = None
    created_at: datetime = Field(default_factory=get_utc_now)


class Variety(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    species_id: int = Field(foreign_key="species.id")
    description: str | None = None
    qr_code_path: str | None = None
    created_at: datetime = Field(default_factory=get_utc_now)


class Rack(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: int | None = Field(default=None, primary_key=True)
    rack_identifier: str = Field(index=True, unique=True)
    variety_id: int = Field(foreign_key="variety.id")
    name: str | None = Field(default=None)
    description: str | None = Field(default=None)

    qr_code_path: str | None = None
    image_url: str | None = None
    metadata_json: str = Field(default="{}")

    created_at: datetime = Field(default_factory=get_utc_now)

    @property
    def metadata_dict(self) -> dict:
        try:
            value = json.loads(self.metadata_json)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(
                "Rack metadata contains invalid JSON. Repair the original data before editing."
            ) from exc
        if not isinstance(value, dict):
            raise ValueError(
                "Rack metadata must be a JSON object. Repair the original data before editing."
            )
        return value


class Vessel(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: int | None = Field(default=None, primary_key=True)
    vessel_identifier: str = Field(index=True, unique=True)
    rack_id: int = Field(foreign_key="rack.id", index=True)
    name: str | None = None
    passage_number: int = Field(default=0, ge=0)
    medium_batch: str | None = None
    subculture_date: date | None = None
    contamination_status: str = "Unknown"
    notes: str | None = None
    created_at: datetime = Field(default_factory=get_utc_now)
