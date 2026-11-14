"""A saved area comes back unchanged; same area, same identifier; nothing invented."""

from fastapi.testclient import TestClient


def test_zones(app, tmp_path):
    application, zone, _, _ = app
    with TestClient(application) as client:
        r = client.post("/api/zones", json={"body": "moon", "h3_cells": zone})
        assert r.status_code == 200, r.text
        ident = r.json()["id"]
        assert client.post("/api/zones", json={"body": "moon", "h3_cells": zone[::-1]}).json()["id"] == ident
        d = client.get(f"/api/zones/{ident}").json()
        assert d["body"] == "moon" and sorted(d["h3_cells"]) == sorted(zone)
        assert (tmp_path / "cache" / "zones" / f"{ident}.json").is_file()
        assert client.get("/api/zones/0123456789ab").status_code == 404
        assert client.get("/api/zones/..%2Fsecret").status_code == 404
        assert client.post("/api/zones", json={"body": "mars", "h3_cells": ["zz"]}).status_code == 422
