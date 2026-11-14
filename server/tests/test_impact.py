"""Field campaign impact: protected shares averaged over the footprint, filter, site card and WDPA citation."""

import json

import h3
import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient


def write_impact(folder, target):
    """The target and its footprint in a protected area; an airport 42 km from every cell."""
    d = folder / "environmental_impact"
    d.mkdir(parents=True, exist_ok=True)
    earth = list(h3.grid_disk(h3.latlng_to_cell(30, 10, 5), 15))
    protected = set(h3.grid_disk(target, 5))
    t = pa.table({"body": ["earth"] * len(earth), "resolution": [5] * len(earth), "h3": earth,
                  "part_protegee": [1.0 if c in protected else 0.0 for c in earth],
                  "part_protegee_stricte": [0.0] * len(earth),
                  "distance_aeroport_km": [42.0] * len(earth),
                  "aeroport_nom": ["Test Airport"] * len(earth), "aeroport_code": ["TST"] * len(earth)})
    meta = {b"sources": json.dumps({"aires_protegees": "WDPA", "wdpa_version": "Nov2026"}).encode()}
    pq.write_table(t.replace_schema_metadata(meta), d / "environmental_impact_earth_h3_5.parquet")


def test_impact(app, tmp_path):
    application, zone, target, _ = app
    write_impact(tmp_path, target)
    with TestClient(application) as client:
        r = client.post("/api/search", json={"body": "mars", "h3_cells": zone}).json()
        P = r["pool"]
        i = P["h3"].index(target)
        assert P["impact"]["protected"][i] == 1.0 and P["impact"]["airport_km"][i] == 42
        assert "November 2026" in P["impact"]["source"]

        f = client.post("/api/search", json={"body": "mars", "h3_cells": zone, "filters": {"max_protected": 0.3}}).json()
        assert target not in f["pool"]["h3"]                   # discarded: its cell is protected
        assert "protected areas ≤ 30%" in f["funnel"][1]["message"]

        d = client.get(f"/api/site/{target}").json()
        campaign = next(s for s in d["sections"] if s["name"] == "Field campaign")
        assert campaign["items"][0] == {"label": "Protected area", "value": 100.0, "unit": "%"}
        assert campaign["items"][-1]["value"] == "Test Airport (TST), 42 km"
        assert "November 2026" in d["sources"]["protected_areas"]


def test_without_impact(app):
    """Without the module, the search works as before and returns no impact block."""
    application, zone, _, _ = app
    with TestClient(application) as client:
        r = client.post("/api/search", json={"body": "mars", "h3_cells": zone}).json()
        assert r["pool"]["impact"] is None
