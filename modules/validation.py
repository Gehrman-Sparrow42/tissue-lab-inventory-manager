# Callers handle malformed stored or submitted metadata uniformly as ValueError.
# ruff: noqa: TRY004
import json
import math

from sqlmodel import select


def _number(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number.")
    return number


def validate_metadata_schema(schema_str: str):
    """Validate and normalize a species schema without changing stored values."""
    try:
        schema = json.loads(schema_str)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Metadata schema must contain valid JSON.") from exc
    if not isinstance(schema, list):
        raise ValueError("Schema must be a JSON array (list).")
    normalized = []
    names = set()
    for item in schema:
        if not isinstance(item, dict):
            raise ValueError("Each schema item must be an object.")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Each schema item must have a non-empty text name.")
        name = name.strip()
        if name in names:
            raise ValueError(f"Duplicate schema field name '{name}'. Use unique names.")
        names.add(name)
        field_type = item.get("type", "text")
        if field_type not in ("text", "number"):
            raise ValueError(f"Field '{name}' must have type 'text' or 'number'.")
        field = dict(item, name=name, type=field_type)
        if field_type == "number":
            field["default"] = _number(item.get("default", 0), f"Default for '{name}'")
        else:
            default = item.get("default", "")
            if not isinstance(default, str):
                raise ValueError(f"Default for '{name}' must be text.")
            field["default"] = default
        normalized.append(field)
    return normalized


def reconcile_metadata(metadata: dict, schema_str: str) -> dict:
    """Add missing fields, retaining removed fields and incompatible old values."""
    if not isinstance(metadata, dict):
        raise ValueError("Rack metadata must be a JSON object.")
    result = dict(metadata)
    for field in validate_metadata_schema(schema_str):
        result.setdefault(field["name"], field["default"])
    return result


def validate_metadata_values(metadata: dict, schema_str: str) -> dict:
    result = reconcile_metadata(metadata, schema_str)
    for field in validate_metadata_schema(schema_str):
        name = field["name"]
        if field["type"] == "number":
            result[name] = _number(result[name], name)
        elif not isinstance(result[name], str):
            result[name] = str(result[name])
    return result


def migrate_racks_metadata(
    session, species_id: int, old_schema_str: str, new_schema_str: str
):
    """Stage non-destructive migration in the caller's transaction."""
    from modules.models import Rack, Variety

    validate_metadata_schema(new_schema_str)
    racks = session.exec(
        select(Rack)
        .join(Variety, Rack.variety_id == Variety.id)
        .where(Variety.species_id == species_id)
    ).all()
    for rack in racks:
        try:
            metadata = reconcile_metadata(rack.metadata_dict, new_schema_str)
        except ValueError as exc:
            raise ValueError(
                f"Repair metadata for rack '{rack.rack_identifier}' before changing its species schema."
            ) from exc
        rack.metadata_json = json.dumps(metadata, ensure_ascii=False)
        session.add(rack)
