"""Shared inventory shell and presentation primitives."""

from html import escape
from pathlib import Path
from urllib.parse import urlencode

import streamlit as st

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
