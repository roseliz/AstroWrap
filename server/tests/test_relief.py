"""3D view: terrain read from a simple cylindrical mosaic (like MOLA) and from Copernicus tiles, without network;
fast reading of an untiled remote GeoTIFF (the USGS LOLA mosaic): same values as GDAL, far fewer bytes."""

import base64
import http.server
import math
import os
import re
import threading

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
pytest.importorskip("PIL")


def _truth(lat, lon):
    return 1000 * np.sin(np.radians(lon) * 3) + 500 * np.cos(np.radians(lat) * 5)


@pytest.fixture
def sources(tmp_path, monkeypatch):
    from rasterio.transform import from_origin
    from server.core import config
    from server.services import relief
    # Mars: global mosaic in meters (x = Rλ, y = Rφ), 0.25° per pixel
    R, step = 3_396_190.0, 0.25
    W, H = int(360 / step), int(180 / step)
    lons = -180 + (np.arange(W) + 0.5) * step
    lats = 90 - (np.arange(H) + 0.5) * step
    LON, LAT = np.meshgrid(lons, lats)
    m = math.radians(step) * R
    with rasterio.open(tmp_path / "mola.tif", "w", driver="GTiff", width=W, height=H, count=1, dtype="float32",
                       crs="+proj=eqc +R=3396190 +units=m +no_defs",
                       transform=from_origin(-math.pi * R, math.pi / 2 * R, m, m)) as d:
        d.write(_truth(LAT, LON).astype("float32"), 1)
    # Earth: two Copernicus tiles, the rest is ocean
    cop = tmp_path / "cop"
    cop.mkdir()
    names = []
    for la, lo in [(45, 6), (45, 7)]:
        name = relief._copernicus_name(la, lo)
        names.append(name)
        n = 120
        lo_c = lo + (np.arange(n) + 0.5) / n
        la_c = la + 1 - (np.arange(n) + 0.5) / n
        X, Y = np.meshgrid(lo_c, la_c)
        with rasterio.open(cop / f"{name}.tif", "w", driver="GTiff", width=n, height=n, count=1, dtype="float32",
                           crs="EPSG:4326", transform=from_origin(lo, la + 1, 1 / n, 1 / n)) as d:
            d.write(_truth(Y, X).astype("float32"), 1)
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    (tmp_path / "cache" / "relief").mkdir(parents=True)
    (tmp_path / "cache" / "relief" / "copernicus_tileList.txt").write_text("\n".join(names))
    monkeypatch.setitem(relief.DEM, "mars", [tmp_path / "mola.tif"])
    monkeypatch.setattr(relief, "COPERNICUS", [cop])
    from PIL import Image
    monkeypatch.setattr(relief, "_tile", lambda url, path: Image.new("RGB", (256, 256), (200, 120, 60)))
    return relief


def _heights(r):
    return np.frombuffer(base64.b64decode(r["heights_i16"]), "<i2").reshape(r["n"], r["n"]).astype(float)


def test_mars_and_antimeridian(sources):
    for lon in (40.0, 179.9):                          # 179.9°: the square crosses to the other side of -180°
        r = sources.relief("mars", 20.0, lon, 200, n=65)
        la, lo = sources.grid(20.0, lon, 200, 65, sources.RADIUS_KM["mars"])
        assert np.abs(_heights(r) - _truth(la, lo)).max() < 15, lon
        assert r["texture"].startswith("data:image/jpeg")
        assert abs(r["grid_m"] - 200_000 / 64) < 1


def test_pole(sources):
    r = sources.relief("mars", 89.9, 0.0, 100, n=33)   # every longitude
    la, lo = sources.grid(89.9, 0.0, 100, 33, sources.RADIUS_KM["mars"])
    assert np.abs(_heights(r) - _truth(la, lo)).max() < 30


def test_earth_and_ocean(sources):
    r = sources.relief("earth", 45.5, 7.0, 60, n=65)
    la, lo = sources.grid(45.5, 7.0, 60, 65, sources.RADIUS_KM["earth"])
    assert np.abs(_heights(r) - _truth(la, lo)).max() < 15
    r = sources.relief("earth", 45.5, 5.9, 40, n=33)    # western half: no tile = ocean, 0 m
    la, lo = sources.grid(45.5, 5.9, 40, 33, sources.RADIUS_KM["earth"])
    h = _heights(r)
    assert (h[lo < 6] == 0).all() and np.abs(h[lo > 6.05] - _truth(la, lo)[lo > 6.05]).max() < 15
    water = np.frombuffer(base64.b64decode(r["water_u8"]), np.uint8).reshape(33, 33).astype(bool)
    assert water[lo < 5.99].all() and not water[lo > 6.01].any()


def test_route(sources, app):
    from fastapi.testclient import TestClient
    application, _, _, _ = app
    with TestClient(application) as client:
        r = client.get("/api/relief", params={"body": "mars", "lat": 10, "lon": 20, "size_km": 120, "n": 64})
        assert r.status_code == 200, r.text
        assert r.json()["n"] == 64 and len(base64.b64decode(r.json()["heights_i16"])) == 64 * 64 * 2
        assert client.get("/api/relief", params={"body": "venus", "lat": 0, "lon": 0}).status_code == 422
        assert client.get("/api/relief", params={"body": "mars", "lat": 0, "lon": 0, "size_km": 5000}).status_code == 422


class _RangeHandler(http.server.BaseHTTPRequestHandler):
    """Serves a file with Range headers, and counts the bytes sent."""
    protocol_version = "HTTP/1.1"
    path_on_disk, bytes_sent = None, 0

    def log_message(self, *a):
        pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", str(os.path.getsize(self.path_on_disk)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def do_GET(self):
        size = os.path.getsize(self.path_on_disk)
        m = re.match(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
        a, b = (int(m.group(1)), min(size - 1, int(m.group(2) or size - 1))) if m else (0, size - 1)
        with open(self.path_on_disk, "rb") as f:
            f.seek(a)
            d = f.read(b - a + 1)
        type(self).bytes_sent += len(d)
        self.send_response(206 if m else 200)
        self.send_header("Content-Length", str(len(d)))
        self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
        self.end_headers()
        self.wfile.write(d)


def test_remote_rows(tmp_path, monkeypatch):
    from rasterio.transform import from_origin
    from server.services import relief

    W, H = 4000, 2000
    f = tmp_path / "moon.tif"
    y, x = np.mgrid[0:H, 0:W]
    z = (1000 * np.sin(x / 90.0) * np.cos(y / 70.0)).astype("int16")
    with rasterio.open(f, "w", driver="GTiff", width=W, height=H, count=1, dtype="int16", tiled=False,
                       crs="+proj=longlat +R=1737400 +no_defs", transform=from_origin(-180, 90, 0.09, 0.09)) as d:
        d.write(z, 1)
    _RangeHandler.path_on_disk = str(f)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RangeHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    for v in ("NO_PROXY", "no_proxy"):
        monkeypatch.setenv(v, "127.0.0.1")
    url = f"http://127.0.0.1:{server.server_port}/moon.tif"
    try:
        with rasterio.open(f"/vsicurl/{url}") as src:
            _RangeHandler.bytes_sent = 0
            fast = relief._read_rows(src, url, 500, 900, relief._spans(W, 3800, 4200), 4)   # wraps around at 180°
            sent = _RangeHandler.bytes_sent
        assert fast is not None
        a, sy, sx = fast
        assert a.shape == (100, 100) and sy == 4 and sx == 4
        expected = np.hstack([z[500:900, 3800:], z[500:900, :200]]).astype(float)
        expected = expected.reshape(100, 4, 100, 4).mean(axis=(1, 3))
        assert np.abs(a - expected).mean() < 15                 # 2 rows out of 4 read: close to the exact mean
        assert sent < 0.2 * 400 * W * 2                         # far less than the 400 whole rows
    finally:
        server.shutdown()
