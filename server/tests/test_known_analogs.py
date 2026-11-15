"""Known analogs: returned with the search in the pool format, only those of the body, never in the ranking."""

import h3
from fastapi.testclient import TestClient


def test_known_analogs(app, monkeypatch):
    import server.services.known_analogs as K
    application, zone, target, cells = app
    la, lo = h3.cell_to_latlng(target)
    tl, tlo = h3.cell_to_latlng(cells["trap"])
    common = dict(country="", scope="environment", analog_of="", source="")
    monkeypatch.setattr(K, "CATALOG", [
        dict(common, id="target", bodies=("mars",), name="Target", lat=la, lon=lo),
        dict(common, id="trap", bodies=("mars",), name="Trap", lat=tl, lon=tlo),
        dict(common, id="offshore", bodies=("mars",), name="Offshore", lat=-40.0, lon=-30.0),
        dict(common, id="moon", bodies=("moon",), name="Moon", lat=la, lon=lo),
    ])
    with TestClient(application) as client:
        d = client.post("/api/search", json={"body": "mars", "h3_cells": zone}).json()
    known = {a["id"]: a for a in d["known"]}
    assert set(known) == {"target", "trap", "offshore"}                 # only those of the body
    assert target in known["target"]["h3"] and len(known["target"]["h3"]) == 7
    assert known["offshore"]["h3"] == []                                 # outside the data: at sea
    i = known["target"]["h3"].index(target)
    assert known["target"]["score_per_module"]["thermal"][i] > 0.99
    j = known["trap"]["h3"].index(cells["trap"])
    assert known["trap"]["score_per_module"]["thermal"][j] < 0.9         # judged over its footprint, not its cell
