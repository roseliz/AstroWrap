"""Card of a cell: module values and Natural Earth region name, without network."""

from fastapi.testclient import TestClient


def test_site_card(app, tmp_path, monkeypatch):
    import shapefile
    import server.services.places as places
    d = tmp_path / "cache" / "natural_earth" / "ne_10m_geography_regions_polys"
    d.mkdir(parents=True)
    w = shapefile.Writer(str(d / "ne_10m_geography_regions_polys"), shapeType=shapefile.POLYGON, encoding="utf-8")
    w.field("featurecla", "C")
    w.field("name", "C")
    w.poly([[[0, 20], [20, 20], [20, 40], [0, 40], [0, 20]]])
    w.record("Desert", "Sahara")
    w.close()
    monkeypatch.setattr(places, "_layers", {"countries": None})       # regions: read from the file above
    application, _, target, _ = app
    with TestClient(application) as client:
        r = client.get(f"/api/site/{target}")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["place"]["name"] == "Sahara" and d["place"]["natural_regions"][0]["kind"] == "desert"
        assert d["sections"][0]["name"] == "Climate"
        assert client.get("/api/site/not-a-cell").status_code == 422
        n = client.post("/api/names", json={"cells": [target]}).json()["names"]
        assert n[target]["name"] == "Sahara" and n[target]["kind"] == "region"
        assert client.post("/api/names", json={"cells": ["not-a-cell"]}).status_code == 422
