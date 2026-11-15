"""End-to-end tests on fake data: the Earth cell identical to the Mars area must come first."""

from fastapi.testclient import TestClient


def test_search(app):
    application, zone, target, cells = app
    with TestClient(application) as client:
        assert client.get("/api/health").status_code == 200
        r = client.post("/api/search", json={"body": "mars", "h3_cells": zone})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["active_modules"] == ["thermal"]
        assert d["best_cells"][0]["score"] > 0.99
        # area against area: the footprint counts, not the single cell. The area has 91 Mars cells, i.e. the
        # surface of ~26 Earth cells (ratio of the squared radii): footprint of 2 rings (19 cells)
        assert d["footprint"]["rings"] == 2
        P, trap, edge = d["pool"], cells["trap"], cells["edge"]
        sim = dict(zip(P["h3"], P["score_per_module"]["thermal"]))
        water = dict(zip(P["h3"], P["water_share"]))
        assert sim[target] > 0.99 and water[target] == 0
        assert sim[trap] < 0.9 < dict(zip(P["h3"], P["cell_score_per_module"]["thermal"]))[trap]
        assert water[edge] > 0.3 and sim[edge] > 0.99
        assert d["funnel"][0]["type"] == "progress" and d["funnel"][-1]["type"] == "done"
        det = client.post("/api/search/detail", json={"body": "mars", "h3_cells": zone, "cell": target}).json()
        assert det["modules"][0]["similarity"] > 0.99
        assert det["footprint"]["rings"] == 2 and len(det["footprint"]["cells"]) == 19
        assert det["footprint"]["water_share"] == 0
        assert client.post("/api/search", json={"body": "venus", "h3_cells": zone}).status_code == 422
        assert client.post("/api/search", json={"body": "mars", "h3_cells": []}).status_code == 422


def test_meta(app):
    application, _, _, _ = app
    with TestClient(application) as client:
        modules = {m["key"]: m for m in client.get("/api/modules").json()["modules"]}
        assert modules["thermal"]["available"]["earth"] and not modules["wind"]["available"]["mars"]
        presets = {p["key"]: p for p in client.get("/api/presets").json()["presets"]}
        assert presets["landing"]["weights"]["topography"] == 3


def test_funnel_tolerance():
    """One criterion below the Earth's median is forgiven from three active criteria, none below."""
    from server.services import combine
    assert [combine.tolerated_misses(n) for n in (1, 2, 3, 6)] == [0, 0, 1, 1]


def test_terrain(app, tmp_path):
    """Flat ground share per resolution-5 cell of the area, mean weighted by the painted tiles."""
    import h3
    import pandas as pd
    application, zone, _, _ = app
    parents = sorted({h3.cell_to_parent(c, 5) for c in zone})
    d = tmp_path / "topography_morphometry"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"h3": parents[1:], "part_pente_inf_5": [0.2] + [1.0] * (len(parents) - 2)}) \
        .assign(resolution=5, body="mars").to_parquet(d / "topography_morphometry_mars_h3_5_b500.parquet")
    with TestClient(application) as client:
        r = client.post("/api/zones/terrain", json={"body": "mars", "h3_cells": zone})
        assert r.status_code == 200, r.text
        t = r.json()
        assert parents[0] not in t["cells"] and t["cells"][parents[1]] == 0.2 and t["threshold"] == 0.5
        assert abs(t["flat"] - (0.2 + len(parents) - 2) / (len(parents) - 1)) < 1e-3
        assert client.post("/api/zones/terrain", json={"body": "moon", "h3_cells": zone}).json()["flat"] is None
