"""Name of a place on the Earth: natural region (Natural Earth), locality, region and country (OpenStreetMap).

- Natural Earth, offline after a first download (~7 MB, in server/cache/): ne_10m_geography_regions_polys
  (deserts, mountain ranges, plateaus, basins: "Atacama", "Tibetan Plateau") and ne_10m_admin_0_countries
  (countries, if OpenStreetMap does not answer).
- OpenStreetMap Nominatim (online): locality, region, country, in English. Usage policy: at most one request per
  second, a User-Agent that identifies the application, cached results; the interface shows
  "© OpenStreetMap contributors".
Without network or cache, the place is just its coordinates: nothing breaks.
"""

import json
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

from ..core import config

NE_URL = "https://naciscdn.org/naturalearth/10m/{group}/{name}.zip"
LAYERS = {"regions": ("physical", "ne_10m_geography_regions_polys"),
          "countries": ("cultural", "ne_10m_admin_0_countries")}
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "astrowrap/1.0 (NASA Space Apps Challenge 2026, github.com/roseliz/NasaChallenges)"
CATEGORIES = {"Desert": "desert", "Range/mtn": "mountain range", "Plateau": "plateau", "Basin": "basin",
              "Plain": "plain", "Tundra": "tundra", "Valley": "valley", "Peninsula": "peninsula",
              "Island group": "archipelago", "Island": "island", "Lowland": "lowland", "Delta": "delta",
              "Wetlands": "wetlands", "Geoarea": "region", "Coast": "coast", "Gorge": "gorge",
              "Depression": "depression", "Foothills": "foothills", "Isthmus": "isthmus", "Cape": "cape",
              "Pen/cape": "cape", "Plain/tundra": "tundra"}

CONTINENTS = {"Continent"}                     # featurecla of the continents in geography_regions_polys
_layers = {}
_lock = threading.Lock()
_osm_cache = {}
_last_call = [0.0]
_osm_lock = threading.Lock()


# ---------------------------------------------------------------------- Natural Earth
class Layer:
    """Polygons of a layer, with their bounding box, to test a point."""

    def __init__(self, path: Path):
        import shapefile                                       # pyshp
        r = shapefile.Reader(str(path), encoding="utf-8", encodingErrors="replace")
        self.items = []
        for sr in r.iterShapeRecords():
            s = sr.shape
            if not s.points:
                continue
            pts = np.asarray(s.points, dtype=float)
            bounds = list(s.parts) + [len(pts)]
            rings = [pts[bounds[k]:bounds[k + 1]] for k in range(len(s.parts))]
            area = sum(abs(ring_area(a)) for a in rings)
            self.items.append((tuple(s.bbox), rings, area, sr.record.as_dict()))

    def containing(self, lat, lon) -> list:
        """Records of the polygons that contain the point, from smallest to largest."""
        found = []
        for (x0, y0, x1, y1), rings, area, rec in self.items:
            if x0 <= lon <= x1 and y0 <= lat <= y1 and inside(rings, lon, lat):
                found.append((area, rec))
        return [rec for _, rec in sorted(found, key=lambda t: t[0])]


def ring_area(a):
    x, y = a[:, 0], a[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def inside(rings, x, y) -> bool:
    """Even-odd rule over every ring (holes are handled naturally)."""
    c = False
    for a in rings:
        xi, yi = a[:, 0], a[:, 1]
        xj, yj = np.roll(xi, 1), np.roll(yi, 1)
        crosses = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / np.where(yj != yi, yj - yi, 1e-30) + xi)
        c ^= bool(np.count_nonzero(crosses) % 2)
    return c


def download(group, name) -> Path:
    folder = config.CACHE_DIR / "natural_earth" / name
    shp = folder / f"{name}.shp"
    if shp.is_file():
        return shp
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder.with_suffix(".zip")
    req = urllib.request.Request(NE_URL.format(group=group, name=name), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r, open(archive, "wb") as f:
        f.write(r.read())
    with zipfile.ZipFile(archive) as z:
        z.extractall(folder)
    archive.unlink(missing_ok=True)
    return shp


def layer(key):
    with _lock:
        if key not in _layers:
            try:
                _layers[key] = Layer(download(*LAYERS[key]))
            except Exception as e:          # noqa: BLE001: no network, pyshp missing...
                print(f"  Natural Earth {LAYERS[key][1]} unavailable: {e}", flush=True)
                _layers[key] = None
        return _layers[key]


def load_in_background():
    threading.Thread(target=lambda: [layer(k) for k in LAYERS], daemon=True).start()


def field(rec: dict, *names):
    for n in names:
        for k in (n, n.upper(), n.lower()):
            v = rec.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


# ---------------------------------------------------------------------- OpenStreetMap
def nominatim(lat, lon):
    key = (round(lat, 3), round(lon, 3))
    if key in _osm_cache:
        return _osm_cache[key]
    q = urllib.parse.urlencode({"format": "jsonv2", "lat": f"{lat:.5f}", "lon": f"{lon:.5f}", "zoom": 10,
                                "accept-language": "en"})
    with _osm_lock:
        wait = 1.05 - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        try:
            req = urllib.request.Request(f"{NOMINATIM_URL}?{q}", headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=8) as r:
                d = json.loads(r.read().decode("utf-8"))
        except Exception:                   # noqa: BLE001: offline, rate limit reached...
            d = None
        finally:
            _last_call[0] = time.time()
    if d is not None and "error" not in d:
        _osm_cache[key] = d
    return d if d is not None and "error" not in d else None


# ---------------------------------------------------------------------- place name
def place(lat: float, lon: float, online: bool = True) -> dict:
    """Name of the place; online=False: Natural Earth only (instant, without Nominatim's queue)."""
    out = {"name": None, "natural_regions": [], "locality": None, "county": None, "state": None,
           "country": None, "country_code": None, "sources": []}
    regions = layer("regions")
    if regions is not None:
        for rec in regions.containing(lat, lon)[:4]:
            name = field(rec, "name_en", "name")
            cat = field(rec, "featurecla")
            if name and cat not in CONTINENTS:           # "Asia", "Africa": too vague to name a site
                out["natural_regions"].append({"name": name, "kind": CATEGORIES.get(cat, cat.lower() if cat else None)})
        if out["natural_regions"]:
            out["sources"].append("Natural Earth")
    osm = nominatim(lat, lon) if online else None
    if osm:
        a = osm.get("address", {})
        out["locality"] = next((a[k] for k in ("village", "town", "city", "hamlet", "municipality", "suburb")
                                if a.get(k)), None)
        out["county"] = a.get("county") or a.get("state_district")
        out["state"] = a.get("state") or a.get("region") or a.get("province")
        out["country"] = a.get("country")
        out["country_code"] = (a.get("country_code") or "").upper() or None
        out["osm_name"] = osm.get("name") or None
        out["sources"].append("OpenStreetMap")
    if not out["country"]:
        countries = layer("countries")
        if countries is not None:
            recs = countries.containing(lat, lon)
            if recs:
                out["country"] = field(recs[0], "NAME_EN", "NAME", "ADMIN")
                out["country_code"] = field(recs[0], "ISO_A2_EH", "ISO_A2")
                if "Natural Earth" not in out["sources"] and out["country"]:
                    out["sources"].append("Natural Earth")
    out["name"] = (out["natural_regions"][0]["name"] if out["natural_regions"] else None) \
        or out.get("osm_name") or out["locality"] or out["county"] or out["state"] or out["country"]
    return out
