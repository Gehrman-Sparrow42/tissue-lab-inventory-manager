"""Readable inventory and self-contained printable label exports."""

import base64
import csv
import html
import io
import json

from sqlmodel import select

from modules.models import Rack, Species, Variety, Vessel
from modules.qr_utils import generate_qr_code, get_qr_bytes


def inventory_rows(session):
    species = session.exec(select(Species)).all()
    varieties = session.exec(select(Variety)).all()
    racks = session.exec(select(Rack)).all()
    vessels = session.exec(select(Vessel)).all()
    smap = {s.id: s for s in species}
    vmap = {v.id: v for v in varieties}
    rmap = {r.id: r for r in racks}
    rows = []

    def add(kind, obj, s=None, v=None, r=None):
        data = obj.model_dump()
        rows.append(
            {
                "level": kind,
                "species": s.name if s else "",
                "variety": v.name if v else "",
                "rack": r.rack_identifier if r else "",
                **data,
            }
        )

    for s in species:
        add("species", s, s)
    for v in varieties:
        add("variety", v, smap.get(v.species_id), v)
    for r in racks:
        v = vmap.get(r.variety_id)
        add("rack", r, smap.get(v.species_id) if v else None, v, r)
    for vessel in vessels:
        r = rmap.get(vessel.rack_id)
        v = vmap.get(r.variety_id) if r else None
        add("vessel", vessel, smap.get(v.species_id) if v else None, v, r)
    return rows


def _csv_value(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    value = str(value)
    if value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) or value.startswith(
        ("\t", "\r", "\n")
    ):
        return "'" + value
    return value


def inventory_csv(session):
    rows = inventory_rows(session)
    columns = list(dict.fromkeys(key for row in rows for key in row)) or [
        "level",
        "species",
        "variety",
        "rack",
    ]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    writer.writerows(
        {key: _csv_value(value) for key, value in row.items()} for row in rows
    )
    return stream.getvalue().encode("utf-8-sig")


def printable_labels(session):
    labels = []
    for row in inventory_rows(session):
        kind = row["level"]
        identifier = (
            row.get("rack_identifier")
            if kind == "rack"
            else row.get("vessel_identifier")
            if kind == "vessel"
            else row.get("id")
        )
        title = row.get("name") or identifier
        image = base64.b64encode(
            get_qr_bytes(generate_qr_code(str(identifier), kind))
        ).decode("ascii")
        labels.append(
            f'<article><img src="data:image/png;base64,{image}" alt="QR code"><div><strong>{html.escape(str(title))}</strong><br>{html.escape(kind.title())}: {html.escape(str(identifier))}</div></article>'
        )
    return (
        """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Inventory QR labels</title><style>
    body{font:14px sans-serif;margin:16px} .grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
    article{border:1px solid #777;padding:8px;display:flex;align-items:center;gap:8px;min-width:0;break-inside:avoid;overflow-wrap:anywhere}
    img{width:85px;height:85px;flex:none}
    @media screen and (max-width:800px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media screen and (max-width:500px){.grid{grid-template-columns:minmax(0,1fr)}}
    @media print{body{margin:0}.instructions{display:none}article{page-break-inside:avoid}}
    </style></head><body><p class="instructions">Print this page using your browser’s print command.</p><main class="grid">"""
        + "".join(labels)
        + "</main></body></html>"
    ).encode("utf-8")
