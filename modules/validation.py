from sqlmodel import select
import json

def validate_metadata_schema(schema_str: str):
    """Validates that schema is a JSON array of objects, each containing a 'name' key."""
    schema = json.loads(schema_str)
    if not isinstance(schema, list):
        raise ValueError("Schema must be a JSON array (list).")
    for item in schema:
        if not isinstance(item, dict):
            raise ValueError("Each schema item must be an object (dictionary).")
        if "name" not in item or not item["name"].strip():
            raise ValueError("Each schema item must contain a non-empty 'name' field.")
        if "type" in item and item["type"] not in ["text", "number"]:
            raise ValueError("Schema item 'type' must be 'text' or 'number'.")
    return schema

def migrate_racks_metadata(session, species_id: int, old_schema_str: str, new_schema_str: str):
    """Syncs existing racks' metadata when a species schema is modified."""
    from modules.models import Variety, Rack
    try:
        old_schema = json.loads(old_schema_str)
        new_schema = json.loads(new_schema_str)
    except:
        return
        
    old_fields = {f["name"]: f for f in old_schema if "name" in f}
    new_fields = {f["name"]: f for f in new_schema if "name" in f}
    
    varieties = session.exec(select(Variety).where(Variety.species_id == species_id)).all()
    v_ids = [v.id for v in varieties]
    if not v_ids:
        return
        
    racks = session.exec(select(Rack).where(Rack.variety_id.in_(v_ids))).all()
    for rack in racks:
        meta = rack.metadata_dict
        updated = False
        # Remove old keys
        for key in list(meta.keys()):
            if key not in new_fields:
                del meta[key]
                updated = True
        # Add new keys with defaults
        for fname, ffield in new_fields.items():
            if fname not in meta:
                meta[fname] = ffield.get("default", "")
                updated = True
        if updated:
            rack.metadata_json = json.dumps(meta)
            session.add(rack)
    session.commit()
