import streamlit as st

from modules.validation import reconcile_metadata, validate_metadata_schema


def render_metadata_fields(schema_str, current_metadata, prefix):
    """Render active fields while retaining metadata outside the current schema."""
    schema = validate_metadata_schema(schema_str)
    values = reconcile_metadata(current_metadata, schema_str)
    cols = st.columns(2)
    for index, field in enumerate(schema):
        name = field["name"]
        value = values.get(name, "")
        with cols[index % 2]:
            values[name] = st.text_input(
                name, value="" if value is None else str(value), key=f"{prefix}_{index}"
            )
    return values
