"""Shared inventory shell and presentation primitives."""

import base64
import os
from html import escape
from pathlib import Path
from urllib.parse import urlencode

import streamlit as st

from modules.image_utils import get_image_path

ROOT = Path(__file__).resolve().parents[1]


def setup_page(title, active):
    st.set_page_config(
        page_title=f"{title} · Lab Inventory",
        layout="wide",
        initial_sidebar_state="auto",
    )
    css = (ROOT / "assets" / "ui.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    with st.sidebar:
        st.markdown(
            """<div class="lab-brand"><svg aria-hidden="true" viewBox="0 0 32 32" width="32" height="32"><rect x="2" y="2" width="12" height="12" rx="3" fill="#9cbcff"/><rect x="18" y="2" width="12" height="12" rx="3" fill="#dbe7ff"/><rect x="2" y="18" width="12" height="12" rx="3" fill="#dbe7ff"/><rect x="18" y="18" width="12" height="12" rx="3" fill="#6b96ec"/></svg><span>Lab Inventory<small>Tissue culture workspace</small></span></div>""",
            unsafe_allow_html=True,
        )
        for key, path, label in (
            ("overview", "main.py", "Overview"),
            ("taxonomy", "pages/1_Species_&_Varieties.py", "Species & varieties"),
            ("racks", "pages/2_Racks_&_Assets.py", "Racks & assets"),
            ("vessels", "pages/3_Vessels.py", "Vessels"),
        ):
            st.page_link(path, label=label)
        st.markdown('<div class="sidebar-separator"></div>', unsafe_allow_html=True)


def page_header(title, description):
    st.title(title)
    st.markdown(
        f'<p class="page-description">{escape(description)}</p>', unsafe_allow_html=True
    )


def location_trail(parts):
    items = "".join(
        f"<li>{escape(str(part))}</li>" for part in parts if part is not None
    )
    st.markdown(
        f'<nav class="location-trail" aria-label="Inventory hierarchy"><ol>{items}</ol></nav>',
        unsafe_allow_html=True,
    )


def detail_grid(items):
    fields = "".join(
        f"<div><dt>{escape(str(label))}</dt><dd>{escape(str(value)) if value is not None and str(value) else 'Not recorded'}</dd></div>"
        for label, value in items
    )
    st.markdown(f'<dl class="detail-grid">{fields}</dl>', unsafe_allow_html=True)


def empty_state(title, body):
    st.markdown(
        f'<section class="empty-state"><h3>{escape(title)}</h3><p>{escape(body)}</p></section>',
        unsafe_allow_html=True,
    )


def status_badge(value):
    tone = {"Clean": "clean", "Contaminated": "critical", "Suspected": "warning"}.get(
        str(value), "neutral"
    )
    st.markdown(
        f'<span class="status-badge status-{tone}">{escape(str(value))}</span>',
        unsafe_allow_html=True,
    )


def record_table(rows):
    cells = []
    for row in rows:
        kind = row["level"]
        identifier = (
            row.get("rack_identifier") or row.get("vessel_identifier") or str(row["id"])
        )
        name = row.get("name") or identifier
        location = " / ".join(
            str(row[key]) for key in ("species", "variety", "rack") if row.get(key)
        )
        if kind == "species":
            location = "Species collection"
        elif kind == "variety":
            location = row.get("species") or "Unknown species"
        elif kind == "rack":
            location = " / ".join(
                str(row[key]) for key in ("species", "variety") if row.get(key)
            )
        query = "?" + urlencode({"type": kind, "id": identifier})
        state = row.get("contamination_status") or "—"
        tone = {
            "Clean": "clean",
            "Contaminated": "critical",
            "Suspected": "warning",
        }.get(state, "neutral")
        cells.append(
            f'<tr><td class="record-name"><a href="{escape(query, quote=True)}" target="_blank" rel="noopener noreferrer" aria-label="Open {escape(kind)} {escape(str(identifier), quote=True)}">{escape(str(name))}</a><small>{escape(str(identifier))}</small></td><td class="record-location">{escape(location)}</td><td class="record-kind">{escape(kind.title())}</td><td class="record-state"><span class="status-badge status-{tone}">{escape(state)}</span></td></tr>'
        )
    if not cells:
        cells.append('<tr><td colspan="4">No records match this view.</td></tr>')
    st.markdown(
        '<div class="inventory-wrap"><table class="inventory-table"><caption class="sr-only">Inventory records and their locations</caption><thead><tr><th scope="col">Record</th><th scope="col">Location</th><th scope="col">Type</th><th scope="col">Culture status</th></tr></thead><tbody>'
        + "".join(cells)
        + "</tbody></table></div>",
        unsafe_allow_html=True,
    )


def show_image(image, **kwargs):
    """Keep generated media on the active WebSocket in scaled cloud deployments."""
    if os.getenv("CLOUD_DEPLOYMENT") == "1":
        content = (
            Path(image).read_bytes() if isinstance(image, (str, Path)) else bytes(image)
        )
        mime = "image/png" if content.startswith(b"\x89PNG") else "image/jpeg"
        image = f"data:{mime};base64," + base64.b64encode(content).decode("ascii")
    return st.image(image, **kwargs)


def show_rack_photo(reference, **kwargs):
    image = get_image_path(reference)
    if image:
        return show_image(image, **kwargs)
    return st.markdown(
        """<figure class="rack-photo-placeholder">
<svg viewBox="0 0 240 112" aria-hidden="true" focusable="false">
<g fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M73 65h94v20H73z M82 85v8m76-8v8"/>
<path d="M86 34h14m-12 0v32m10-32v32m15-39h14m-12 0v39m10-39v39m15-32h14m-12 0v32m10-32v32"/>
<path d="M88 55h10m17-8h10m17 8h10"/>
</g>
</svg>
<figcaption>Rack photo unavailable</figcaption>
</figure>""",
        unsafe_allow_html=True,
    )


def download_file(label, data, file_name=None, mime=None, key=None):
    """Serve cloud downloads without instance-local Streamlit media routes."""
    if os.getenv("CLOUD_DEPLOYMENT") != "1":
        return st.download_button(label, data, file_name=file_name, mime=mime, key=key)
    content = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    encoded = base64.b64encode(content).decode("ascii")
    href = f"data:{mime or 'application/octet-stream'};base64,{encoded}"
    st.markdown(
        f'<a class="lab-cloud-download" href="{escape(href, quote=True)}" download="{escape(file_name or "download", quote=True)}">{escape(label)}</a>',
        unsafe_allow_html=True,
    )
    return False
