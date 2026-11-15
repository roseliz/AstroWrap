"""Terrain of an area for the 3D view: elevation grid and satellite image, at the same scale on the three bodies.

Grid: n x n points in an azimuthal equidistant projection centered on (lat, lon), on the body's sphere; x towards
the east, y towards the north, side `size_km`, row 0 at the north. Mars and the Earth get exactly the same grid in
km: the two terrains can be compared by eye, without any scale effect (the radius of Mars is half the Earth's).

Elevation (meters), read in pieces, never whole:
- Mars: MOLA (MGS, 463 m); Moon: LOLA (LRO, 118 m). Local file from the topography preprocessing if it exists
  (inputs/topography_morphometry/mnt_mars, cache/topography_morphometry/...), otherwise remote (GDAL /vsicurl/:
  only the useful parts are downloaded).
- Earth: Copernicus DEM GLO-90 (90 m, 1° tiles, AWS Open Data); no tile = ocean, elevation 0.
Each source is averaged to the size of a grid cell before interpolation: Mars and the Earth therefore get the same
level of detail (the grid's), even though the Earth is measured more finely.

Image: NASA Trek tiles (Mars: Viking mosaic; Moon: LRO WAC) and Esri World Imagery (Earth), assembled here
(no CORS issue in the browser).

Everything is kept in cache/relief/: an area already seen shows up at once. Two identical requests at the same time
(preloading by the main page, then the recap) only do the work once: the second one waits for the first.

Speed on the Moon: the USGS LOLA mosaic (8 GB) is neither tiled nor compressed, one row per strip. GDAL would read
each whole row (184 KB): 230 MB for a 145 km square. _read_rows() only requests the useful bytes (the column span
of a few rows, HTTP requests in parallel): about 1 MB.
"""

import base64
import concurrent.futures as cf
import hashlib
import http.client
import io
import json
import math
import os
import threading
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

from ..core import config

# GDAL settings for remote reading (before the first import of rasterio)
for _key, _val in {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff",
                   "GDAL_HTTP_TIMEOUT": "30", "GDAL_HTTP_MAX_RETRY": "2", "GDAL_HTTP_RETRY_DELAY": "1",
                   "VSI_CACHE": "TRUE", "GDAL_HTTP_USERAGENT": "astrowrap/1.0 (NASA Space Apps 2026)"}.items():
    os.environ.setdefault(_key, _val)

RADIUS_KM = {"earth": 6371.0088, "mars": 3389.5, "moon": 1737.4}
TOPO = "topography_morphometry"
_INPUTS = config.ROOT / "inputs" / TOPO
_TOPO_CACHE = config.ROOT / "cache" / TOPO


def _env(name):
    v = os.environ.get(f"ANALOGUES_{name}")
    return [v] if v else []


# Global mosaics (simple cylindrical, -180..180°), in the order they are tried
DEM = {
    "mars": _env("DEM_MARS") + [
        _INPUTS / "mnt_mars", _TOPO_CACHE / "Mars_MGS_MOLA_DEM_mosaic_global_463m.tif",
        "/vsicurl/https://asc-pds-services.s3.us-west-2.amazonaws.com/wms_basemaps3/Mars/MOLA/"
        "mola128_mola64_merge_90Nto90S_SimpleC_clon0_cog.tif",
        "/vsicurl/https://planetarymaps.usgs.gov/mosaic/Mars_MGS_MOLA_DEM_mosaic_global_463m.tif"],
    "moon": _env("DEM_MOON") + [
        _INPUTS / "mnt_lune", _TOPO_CACHE / "Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif",
        "/vsicurl/https://planetarymaps.usgs.gov/mosaic/Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif"],
}
COPERNICUS = _env("COPERNICUS") + [_TOPO_CACHE / "copernicus",
                                   "/vsicurl/https://copernicus-dem-90m.s3.amazonaws.com/{name}/{name}.tif"]
SOURCES = {"mars": "MOLA (Mars Global Surveyor), 463 m", "moon": "LOLA (Lunar Reconnaissance Orbiter), 118 m",
           "earth": "Copernicus DEM GLO-90, 90 m"}

# Images: (template, scheme, maximum zoom level, credit)
IMAGES = {
    "mars": ("https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0//default/"
             "default028mm/{z}/{y}/{x}.jpg", "geo", 7, "NASA Mars Trek (Viking mosaic)"),
    "moon": ("https://trek.nasa.gov/tiles/Moon/EQ/LRO_WAC_Mosaic_Global_303ppd_v02/1.0.0//default/"
             "default028mm/{z}/{y}/{x}.jpg", "geo", 7, "NASA Moon Trek (LRO WAC)"),
    "earth": ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
              "mercator", 17, "Esri, Maxar, Earthstar Geographics"),
}


# ------------------------------------------------------------------ grid
def grid(lat0: float, lon0: float, size_km: float, n: int, radius_km: float):
    """(lat, lon) in degrees of the n x n points of the azimuthal equidistant grid (row 0 at the north)."""
    d = np.linspace(-size_km / 2, size_km / 2, n)
    x, y = np.meshgrid(d, d[::-1])
    rho = np.hypot(x, y)
    c = rho / radius_km
    p0, l0 = math.radians(lat0), math.radians(lon0)
    with np.errstate(invalid="ignore", divide="ignore"):
        lat = np.arcsin(np.clip(np.cos(c) * math.sin(p0) + np.where(rho > 0, y * np.sin(c) * math.cos(p0) / rho, 0), -1, 1))
        lon = l0 + np.arctan2(x * np.sin(c), rho * math.cos(p0) * np.cos(c) - y * math.sin(p0) * np.sin(c))
    lat = np.where(rho > 0, lat, p0)
    lon = np.where(rho > 0, lon, l0)
    return np.degrees(lat), (np.degrees(lon) + 180) % 360 - 180


def _bilinear(a: np.ndarray, r: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Bilinear interpolation of a at positions (r, c) in pixel indices (centers), NaN skipped when possible."""
    r = np.clip(r, 0, a.shape[0] - 1)
    c = np.clip(c, 0, a.shape[1] - 1)
    r0 = np.floor(r).astype(int)
    c0 = np.floor(c).astype(int)
    r1 = np.minimum(r0 + 1, a.shape[0] - 1)
    c1 = np.minimum(c0 + 1, a.shape[1] - 1)
    fr, fc = r - r0, c - c0
    v = (a[r0, c0] * (1 - fr) * (1 - fc) + a[r0, c1] * (1 - fr) * fc + a[r1, c0] * fr * (1 - fc) + a[r1, c1] * fr * fc)
    nearest = a[np.rint(r).astype(int), np.rint(c).astype(int)]
    return np.where(np.isnan(v), nearest, v)


def _spans(W, c0, c1):
    """Columns c0..c1 split at the edges of the file (wrapping around at -180°)."""
    spans, c = [], c0
    while c < c1:
        start = c % W
        end = min(W, start + (c1 - c))
        spans.append((start, end))
        c += end - start
    return spans


def _read(src, r0, r1, c0, c1, factor):
    """Rows r0..r1 and columns c0..c1 (end excluded; columns beyond the width wrap around), averaged by `factor`;
    returns (float array, actual row step, actual column step)."""
    from rasterio.enums import Resampling
    from rasterio.windows import Window
    h = r1 - r0
    out_h = max(2, math.ceil(h / factor))
    blocks = []
    for start, end in _spans(src.width, c0, c1):
        w = end - start
        out_w = max(1, round(w / factor))
        blocks.append(src.read(1, window=Window(start, r0, w, h), out_shape=(out_h, out_w),
                               resampling=Resampling.average, masked=True).astype("float64").filled(np.nan))
    a = np.hstack(blocks)
    return a, h / out_h, (c1 - c0) / a.shape[1]


# ------------------------------------------------------------------ fast reading of an untiled remote GeoTIFF
_HTTP = threading.local()


def _byte_range(url: str, start: int, end: int) -> bytes:
    """Bytes start..end (inclusive) of a remote file; the connection is kept open per thread (unless behind a proxy)."""
    headers = {"Range": f"bytes={start}-{end}", "User-Agent": os.environ["GDAL_HTTP_USERAGENT"]}
    u = urllib.parse.urlsplit(url)
    if u.scheme == "https" and not urllib.request.getproxies().get("https"):
        for attempt in range(3):
            c = getattr(_HTTP, u.netloc, None)
            if c is None:
                c = http.client.HTTPSConnection(u.netloc, timeout=30)
                setattr(_HTTP, u.netloc, c)
            try:
                c.request("GET", u.path + (f"?{u.query}" if u.query else ""), headers=headers)
                r = c.getresponse()
                d = r.read()
                if r.status == 206:
                    return d
                raise OSError(f"HTTP {r.status}")
            except (OSError, http.client.HTTPException):
                c.close()
                setattr(_HTTP, u.netloc, None)
                if attempt == 2:
                    raise
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        if r.status != 206:
            raise OSError(f"HTTP {r.status}")
        return r.read()


def _read_rows(src, url: str, r0, r1, spans, factor):
    """Like _read, for an uncompressed, untiled remote GeoTIFF (one strip = one row): at most 2 rows read per output
    row, and only the useful column span. None if the file does not lend itself to it."""
    if src.compression is not None or src.count != 1 or src.block_shapes[0] != (1, src.width):
        return None
    itemsize = np.dtype(src.dtypes[0]).itemsize
    h = r1 - r0
    out_h = max(2, math.ceil(h / factor))
    m = max(1, min(factor, 600 // out_h))                   # rows read per output row (at most ~600 requests)
    if sum(e - s for s, e in spans) > src.width / 4:        # near a pole, the rows are almost whole
        m = 1
    rows = r0 + np.minimum(h - 1, ((np.arange(out_h * m) + 0.5) * h / (out_h * m)).astype(int))
    # Start of each row in the file (strips are not necessarily in order: their offsets are read)
    try:
        offset = {int(r): int(src.get_tag_item(f"BLOCK_OFFSET_0_{int(r)}", "TIFF", bidx=1)) for r in np.unique(rows)}
    except (TypeError, ValueError):
        return None
    # Byte order: a small piece read by GDAL is compared with the same piece read here
    from rasterio.windows import Window
    start, end = spans[0]
    n_test = min(64, end - start)
    ref = src.read(1, window=Window(start, int(rows[0]), n_test, 1))[0]
    o = offset[int(rows[0])]
    raw = _byte_range(url, o + start * itemsize, o + (start + n_test) * itemsize - 1)
    dtype = next((t for t in (np.dtype(src.dtypes[0]).newbyteorder("<"), np.dtype(src.dtypes[0]).newbyteorder(">"))
                  if np.array_equal(np.frombuffer(raw, t), ref)), None)
    if dtype is None:
        return None
    nodata = src.nodata
    blocks = []
    for start, end in spans:
        w = end - start
        out_w = max(1, round(w / factor))
        with cf.ThreadPoolExecutor(16) as pool:
            lines = list(pool.map(lambda r: np.frombuffer(_byte_range(url, offset[int(r)] + start * itemsize,
                                                                      offset[int(r)] + end * itemsize - 1), dtype), rows))
        a = np.vstack(lines).astype("float64")
        if nodata is not None:
            a[a == nodata] = np.nan
        a = np.nanmean(a.reshape(out_h, m, w), axis=1)       # mean of the rows read for each output row
        edges = np.linspace(0, w, out_w + 1).astype(int)
        with np.errstate(invalid="ignore"):
            total = np.add.reduceat(np.nan_to_num(a), edges[:-1], axis=1)
            count = np.add.reduceat(np.isfinite(a).astype(float), edges[:-1], axis=1)
            blocks.append(np.where(count > 0, total / np.maximum(count, 1), np.nan))
    a = np.hstack(blocks)
    return a, h / out_h, sum(e - s for s, e in spans) / a.shape[1]


def _mosaic(body: str, lat, lon, step_m: float):
    """Elevation (m) of a global mosaic at the points (lat, lon); (elevations, source name)."""
    import rasterio
    errors = []
    for path in DEM[body]:
        path = str(path)
        if not path.startswith("/vsi"):
            p = Path(path)
            if p.is_dir():
                tifs = sorted(p.glob("*.tif")) + sorted(p.glob("*.tiff"))
                if not tifs:
                    continue
                path = str(max(tifs, key=lambda f: f.stat().st_size))
            elif not p.is_file():
                continue
        try:
            with rasterio.open(path) as src:
                tr, W, H = src.transform, src.width, src.height
                if src.crs is not None and src.crs.is_geographic:
                    per_degree = 1.0
                else:                                       # simple cylindrical in meters: x = Rλ, y = Rφ
                    per_degree = (W * abs(tr.a)) / 360.0    # meters per degree
                lon_w = tr.c / per_degree
                col = ((lon - lon_w) % 360) * per_degree / tr.a - 0.5
                row = (lat * per_degree - tr.f) / tr.e - 0.5
                pixel_m = abs(tr.e) / per_degree * RADIUS_KM[body] * 1000 * math.pi / 180
                factor = max(1, int(step_m / pixel_m))
                cmin, cmax = col.min(), col.max()
                if cmax - cmin > W / 2:                     # crosses -180°: shift the west by one turn
                    col = np.where(col < W / 2, col + W, col)
                    cmin, cmax = col.min(), col.max()
                r0, r1 = max(0, int(row.min()) - 2), min(H, int(row.max()) + 3)
                c0, c1 = int(math.floor(cmin)) - 2, int(math.ceil(cmax)) + 3
                if c1 - c0 >= W:
                    c0, c1 = 0, W
                data = None
                if path.startswith("/vsicurl/http"):
                    try:
                        data = _read_rows(src, path[len("/vsicurl/"):], r0, r1, _spans(W, c0, c1), factor)
                    except Exception:               # noqa: BLE001: fall back to reading through GDAL
                        data = None
                a, sy, sx = data or _read(src, r0, r1, c0, c1, factor)
                scale, offset = float(src.scales[0] or 1.0), float(src.offsets[0] or 0.0)
                if body == "moon" and scale == 1.0 and src.dtypes[0] == "int16":
                    scale = 0.5                             # LDEM as int16: half meters
                dc = (col - c0) % W if c1 - c0 >= W else col - c0
                z = _bilinear(a, (row - r0 + 0.5) / sy - 0.5, (dc + 0.5) / sx - 0.5)
                return z * scale + offset, path.rsplit("/", 1)[-1]
        except Exception as e:                              # source unreachable: try the next one
            errors.append(f"{path.rsplit('/', 1)[-1]}: {e}")
    raise FileNotFoundError(f"no readable terrain model for {body} ({'; '.join(errors) or 'no source'})")


def _copernicus_name(la: int, lo: int) -> str:
    return (f"Copernicus_DSM_COG_30_{'N' if la >= 0 else 'S'}{abs(la):02d}_00_"
            f"{'E' if lo >= 0 else 'W'}{abs(lo):03d}_00_DEM")


_COPERNICUS_LIST = "https://copernicus-dem-90m.s3.amazonaws.com/tileList.txt"


def _copernicus_tiles() -> set:
    """Names of the tiles that exist (the others are ocean); the list is kept in the cache."""
    for f in (_TOPO_CACHE / "copernicus_tileList.txt", config.CACHE_DIR / "relief" / "copernicus_tileList.txt"):
        if f.is_file():
            return set(f.read_text().split())
    text, error = None, "offline"
    if any(str(m).startswith("/vsicurl/") for m in COPERNICUS):
        try:
            req = urllib.request.Request(_COPERNICUS_LIST, headers={"User-Agent": "astrowrap/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                text = r.read().decode()
            f = config.CACHE_DIR / "relief" / "copernicus_tileList.txt"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text)
        except Exception as e:                              # noqa: BLE001
            text, error = None, e
    if text is None:
        # Offline: only the local tiles count
        local = {p.stem for m in COPERNICUS if not str(m).startswith("/vsi") and Path(m).is_dir()
                 for p in Path(m).glob("*.tif")}
        if not local:
            raise FileNotFoundError(f"Copernicus tile list unreachable ({error})")
        return local
    return set(text.split())


def _copernicus(lat, lon, step_m: float):
    """(elevation in m, source, sea mask) of the Earth at the points (lat, lon); the sea (no tile) is 0 m."""
    import rasterio
    existing = _copernicus_tiles()
    z = np.zeros(lat.shape)
    water = np.ones(lat.shape, dtype=bool)              # no tile or no value: sea
    la_t, lo_t = np.floor(lat).astype(int), np.floor(lon).astype(int)
    tiles = [t for t in sorted(set(zip(la_t.ravel().tolist(), lo_t.ravel().tolist())))
             if _copernicus_name(*t) in existing]

    def one(t):
        name = _copernicus_name(*t)
        last = "no source"
        for template in COPERNICUS:
            template = str(template)
            path = template.format(name=name) if "{name}" in template else str(Path(template) / f"{name}.tif")
            if not path.startswith("/vsi") and not Path(path).is_file():
                continue
            try:
                with rasterio.open(path) as src:
                    pixel_m = abs(src.transform.e) * 111_320
                    a, sy, sx = _read(src, 0, src.height, 0, src.width, max(1, int(step_m / pixel_m)))
                    return t, (a, sy, sx, src.transform), None
            except Exception as e:                          # noqa: BLE001
                last = f"{name}: {e}"
        return t, None, last

    errors = []
    with cf.ThreadPoolExecutor(8) as pool:
        for t, data, err in pool.map(one, tiles):
            if data is None:
                errors.append(err)
                continue
            a, sy, sx, tr = data
            m = (la_t == t[0]) & (lo_t == t[1])
            col = (lon[m] - tr.c) / tr.a - 0.5
            row = (lat[m] - tr.f) / tr.e - 0.5
            v = _bilinear(a, (row + 0.5) / sy - 0.5, (col + 0.5) / sx - 0.5)
            z[m] = np.where(np.isnan(v), 0, v)
            water[m] = np.isnan(v) | (np.abs(v) < 0.5)      # the sea of coastal tiles is at 0 m
    if errors:
        raise FileNotFoundError(f"Copernicus DEM: {len(errors)} unreadable tile(s) ({errors[0]})")
    return z, "Copernicus GLO-90", water


# ------------------------------------------------------------------ image
def _tile(url: str, path):
    from PIL import Image
    if path.is_file():
        try:
            return Image.open(path).convert("RGB")
        except OSError:
            pass
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "astrowrap/1.0 (NASA Space Apps 2026)"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        img = Image.open(io.BytesIO(data)).convert("RGB")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return img
    except Exception:                                       # noqa: BLE001
        return None


def image(body: str, lat, lon, step_m: float):
    """Image (n x n x 3, uint8) at the points (lat, lon), or None if no tile arrives."""
    template, scheme, zmax, _ = IMAGES[body]
    R = RADIUS_KM[body] * 1000
    if scheme == "mercator":
        lat_c = float(np.clip(np.median(lat), -85, 85))
        z = math.ceil(math.log2(2 * math.pi * R * math.cos(math.radians(lat_c)) / 256 / step_m))
        z = int(min(zmax, max(1, z)))
        N = 2 ** z * 256
        la = np.radians(np.clip(lat, -85.0511, 85.0511))
        X = (lon + 180) / 360 * N
        Y = (1 - np.log(np.tan(la) + 1 / np.cos(la)) / math.pi) / 2 * N
        cols, rows = 2 ** z, 2 ** z
    else:                                                   # geographic: level z = 2^(z+1) x 2^z tiles
        z = math.ceil(math.log2(math.pi * R / 256 / step_m))
        z = int(min(zmax, max(0, z)))
        X = (lon + 180) / 360 * 2 ** (z + 1) * 256
        Y = (90 - lat) / 180 * 2 ** z * 256
        cols, rows = 2 ** (z + 1), 2 ** z
    tx = (np.floor(X / 256).astype(int)) % cols
    ty = np.clip(np.floor(Y / 256).astype(int), 0, rows - 1)
    wanted = sorted(set(zip(ty.ravel().tolist(), tx.ravel().tolist())))
    if len(wanted) > 400:
        return None, None
    folder = config.CACHE_DIR / "relief" / "tiles" / body / str(z)
    with cf.ThreadPoolExecutor(8) as pool:
        imgs = dict(zip(wanted, pool.map(
            lambda t: _tile(template.format(z=z, y=t[0], x=t[1]), folder / f"{t[0]}_{t[1]}.jpg"), wanted)))
    if not any(v is not None for v in imgs.values()):
        return None, None
    out = np.zeros(lat.shape + (3,), dtype=np.uint8)
    px = (np.floor(X) % 256).astype(int)
    py = np.clip(np.floor(Y) - ty * 256, 0, 255).astype(int)
    for (y_, x_), img in imgs.items():
        if img is None:
            continue
        a = np.asarray(img.resize((256, 256)) if img.size != (256, 256) else img)
        m = (ty == y_) & (tx == x_)
        out[m] = a[py[m], px[m]]
    return out, IMAGES[body][3]


# ------------------------------------------------------------------ terrain of an area
_LOCK = threading.Lock()
_IN_PROGRESS: dict = {}


def relief(body: str, lat: float, lon: float, size_km: float, n: int = 256, n_image: int = 512) -> dict:
    if body not in RADIUS_KM:
        raise ValueError("body must be earth, mars or moon")
    if not (-90 <= lat <= 90 and -180 <= lon <= 360):
        raise ValueError("coordinates out of range")
    key = hashlib.sha256(json.dumps([2, body, round(lat, 3), round(lon, 3), round(size_km, 1), n, n_image]).encode()).hexdigest()[:16]
    path = config.CACHE_DIR / "relief" / f"{key}.json"
    with _LOCK:
        lock = _IN_PROGRESS.setdefault(key, threading.Lock())
    with lock:                                              # same request in progress: wait for its result
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        return _compute(path, body, lat, lon, size_km, n, n_image)


def _compute(path, body, lat, lon, size_km, n, n_image) -> dict:
    import importlib.util
    if not (importlib.util.find_spec("rasterio") and importlib.util.find_spec("PIL")):
        raise FileNotFoundError("the 3D view needs rasterio and pillow: pip install -r requirements.txt")
    R = RADIUS_KM[body]
    step_m = size_km * 1000 / (n - 1)
    la, lo = grid(lat, lon, size_km, n, R)
    water = None
    if body == "earth":
        z, source, water = _copernicus(la, lo, step_m)
    else:
        z, source = _mosaic(body, la, lo, step_m)
    if np.isnan(z).all():
        raise FileNotFoundError(f"no elevation for this area ({source})")
    z = np.where(np.isnan(z), np.nanmedian(z), z)
    la_i, lo_i = grid(lat, lon, size_km, n_image, R)
    img, credit = image(body, la_i, lo_i, size_km * 1000 / n_image)
    texture = None
    if img is not None:
        from PIL import Image
        buffer = io.BytesIO()
        Image.fromarray(img).save(buffer, "JPEG", quality=85)
        texture = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
    z16 = np.clip(np.rint(z), -32768, 32767).astype("<i2")
    p5, p95 = np.percentile(z, [5, 95])
    res = {
        "body": body, "lat": lat, "lon": lon, "size_km": size_km, "n": n,
        "grid_m": round(step_m), "source": SOURCES[body], "file": source,
        "min": float(z.min()), "max": float(z.max()), "relief_p5_p95": float(p95 - p5),
        "heights_i16": base64.b64encode(z16.tobytes()).decode(),
        "texture": texture, "texture_credit": credit,
        # Earth: 1 = sea (no Copernicus tile), n x n bytes
        "water_u8": None if water is None else base64.b64encode(water.astype(np.uint8).tobytes()).decode(),
    }
    if texture is not None:                                 # without an image (network?), try again next time
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(res), encoding="utf-8")
        except OSError:
            pass
    return res
