"""Backtest of the search on reference areas whose Earth analogs are documented: writes ui/data/validation.json,
read by the "Can you trust it?" tab of the How it works page.

    server/.venv/Scripts/python scripts/validation.py [--prod https://api.astrowrap.earth]

Runs the app's own search engine in-process (server/services, imported as is, not modified): the same functions the
API calls, on the same Parquet tables. Nothing of the app is changed, nothing is deployed. What it measures:
1. backtest   rank of each analog's best cell (its cell or a neighbor) among ALL eligible Earth cells (not just
              the ~20,000-cell pool sent to the browser), its rank percentile, and whether it is in the app's top 10;
2. baselines  same cells ranked on the slope distribution alone, and the expectation of a random ranking under
              the same best-of-neighbors rule;
3. stability  each weight × U(0.5, 1.5), 100 runs: share of the top-3 sites still in the top 10; and the same area
              repainted smaller, larger, elongated, shifted;
4. coverage   criteria with data per area, and vegetation, urban and cloud cover of the top 10;
5. timing     engine time of every search (local), and wall time on the deployed API if --prod is given (the only
              HTTP calls: POST /api/search, the request the app itself sends).

The top 10 is rebuilt exactly as the browser builds it (ui/js/analogues.js, recalculer): footprint scores of the
pool, sea share ≤ max_water, confidence ≥ 0.6, no criterion below the Earth median, sites ≥ 800 km apart.
Default weights (all equal), default filter (dense vegetation ≤ 30%). No weight was fitted on these areas.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import random
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import h3
import numpy as np

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
from server.services import combine, db, earth as earth_mod, known_analogs  # noqa: E402
from server.services.scoring.registry import BY_KEY, MODULES  # noqa: E402
SORTIE = RACINE / "ui" / "data" / "validation.json"
RAYON = {"earth": 6371.0088, "mars": 3389.5, "moon": 1737.4}
R6_KM2 = 36.13                     # mean area of a resolution-6 cell on the Earth
ECART_KM = 800                     # default spacing of the interface
VEGETATION_MAX = 0.3               # default filter of the interface
TOP = 10
RUNS = 100

# Earth sites. The catalog of the app (server/services/known_analogs.py) plus Qaidam, added for this test only.
EXTRA = [dict(id="qaidam", name="Qaidam Basin (Dalangtan)", country="China", lat=38.5, lon=91.6,
              scope="environment", analog_of="hyperarid evaporite basin, yardangs", source="Xiao et al. 2017")]

# Reference areas: center, radius, and the analogs the literature pairs with that kind of terrain.
AREAS = [
    dict(id="jezero", body="mars", name="Jezero crater", lat=18.44, lon=77.45, km=20,
         expected=["atacama", "mdrs", "qaidam"], minerals=["salda"]),
    dict(id="gale", body="mars", name="Gale crater (Curiosity)", lat=-4.59, lon=137.44, km=30,
         expected=["atacama", "mdrs", "qaidam"]),
    dict(id="meridiani", body="mars", name="Meridiani Planum (Opportunity)", lat=-1.95, lon=-5.53, km=40,
         expected=["atacama", "qaidam"], minerals=["rio_tinto"]),
    dict(id="shackleton", body="moon", name="Shackleton crater (south pole)", lat=-89.67, lon=129.8, km=10,
         expected=["dry_valleys", "meteor_crater"]),
    dict(id="mare", body="moon", name="Mare Tranquillitatis (Apollo 11)", lat=0.674, lon=23.473, km=25,
         expected=["kilauea", "lanzarote"]),
    dict(id="highland", body="moon", name="Descartes highlands (Apollo 16)", lat=-8.97, lon=15.50, km=25,
         expected=["adirondacks", "meteor_crater"]),
]
# Repainting: (label, radius factor, offset in radii, elongated)
VARIANTS = [("smaller brush", 0.6, 0, False), ("larger brush", 1.6, 0, False),
            ("elongated", 1.0, 0, True), ("shifted", 1.0, 0.5, False)]
GRAND = dict(id="mare_large", label="very large area (Mare, 150 km radius)", km=150)


# ---------------------------------------------------------------------- HTTP (deployed API, timing only)
def appel(url, donnees=None, timeout=600):
    t0 = time.time()
    req = urllib.request.Request(url, data=None if donnees is None else json.dumps(donnees).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    return d, time.time() - t0


# ---------------------------------------------------------------------- areas
def anneaux(km, body):
    n = math.pi * km * km / (R6_KM2 * (RAYON[body] / RAYON["earth"]) ** 2)
    return min(range(400), key=lambda k: abs(3 * k * k + 3 * k + 1 - n))


def deplacer(lat, lon, km, body, cap_deg):
    """Point at km along a bearing, on a sphere of the body's radius."""
    d, t = km / RAYON[body], math.radians(cap_deg)
    la, lo = math.radians(lat), math.radians(lon)
    la2 = math.asin(math.sin(la) * math.cos(d) + math.cos(la) * math.sin(d) * math.cos(t))
    lo2 = lo + math.atan2(math.sin(t) * math.sin(d) * math.cos(la), math.cos(d) - math.sin(la) * math.sin(la2))
    return math.degrees(la2), (math.degrees(lo2) + 540) % 360 - 180


def zone(a, facteur=1.0, decalage=0.0, allonge=False):
    km = a["km"] * facteur
    lat, lon = (deplacer(a["lat"], a["lon"], decalage * a["km"], a["body"], 90) if decalage else (a["lat"], a["lon"]))
    if not allonge:
        return sorted(h3.grid_disk(h3.latlng_to_cell(lat, lon, 6), anneaux(km, a["body"])))
    # elongated: three disks of radius km/√3 along a line, about the same area as the round one
    r = km / math.sqrt(3)
    out = set()
    for d in (-1.6 * r, 0, 1.6 * r):
        p = deplacer(lat, lon, d, a["body"], 90) if d else (lat, lon)
        out |= set(h3.grid_disk(h3.latlng_to_cell(*p, 6), anneaux(r, a["body"])))
    return sorted(out)


# ---------------------------------------------------------------------- browser ranking (analogues.js)
def haversine(la1, lo1, la2, lo2):
    r = math.pi / 180
    a = math.sin((la2 - la1) * r / 2) ** 2 + math.cos(la1 * r) * math.cos(la2 * r) * math.sin((lo2 - lo1) * r / 2) ** 2
    return 2 * RAYON["earth"] * math.asin(math.sqrt(a))


class Reserve:
    """The pool of a search, as arrays, to re-rank it many times like the browser does."""

    def __init__(self, R):
        P = R["pool"]
        self.R, self.h3 = R, P["h3"]
        self.actifs = R["active_modules"]
        f = lambda x: np.array([np.nan if v is None else v for v in x], dtype=float)
        self.sim = {m: f(P["score_per_module"][m]) for m in self.actifs}
        self.rel = {m: np.nan_to_num(f(P["reliability_per_module"][m]), nan=1.0) for m in self.actifs}
        eau = f(P["water_share"])
        self.ok = ~(np.nan_to_num(eau, nan=0) > R["footprint"]["max_water"])
        self.med = R["medians"]
        self.ll = [None] * len(self.h3)
        # gates do not depend on the weights: no criterion below the median (a criterion without data: no miss)
        ecarte = np.zeros(len(self.h3), dtype=bool)
        self.echecs = {}                 # pool cells below the median, per criterion
        for m in self.actifs:
            sous = np.nan_to_num(self.sim[m], nan=np.inf) < self.med[m]
            self.echecs[m] = int(sous.sum())
            ecarte |= sous
        self.ok &= ~ecarte

    def latlng(self, i):
        if self.ll[i] is None:
            self.ll[i] = h3.cell_to_latlng(self.h3[i])
        return self.ll[i]

    def top(self, poids=None, n=TOP, ecart=ECART_KM):
        act = [m for m in self.actifs if (poids or {}).get(m, 1.0) > 0]
        tot = sum((poids or {}).get(m, 1.0) for m in act)
        w = {m: (poids or {}).get(m, 1.0) / tot for m in act}
        s = np.zeros(len(self.h3)); ws = np.zeros(len(self.h3)); mesure = np.zeros(len(self.h3))
        for m in act:
            x = self.sim[m]
            have = np.isfinite(x)
            we = np.where(have, w[m] * (0.5 + 0.5 * self.rel[m]), w[m])
            s += np.where(have, x, self.med[m]) * we
            ws += we
            mesure += np.where(have, w[m], 0)
        score = np.where(self.ok & (mesure >= self.R["confidence_min"]), s / np.maximum(ws, 1e-12), -1)
        out = []
        for i in np.argsort(-score):
            if score[i] < 0:
                break
            la, lo = self.latlng(i)
            if all(haversine(la, lo, c["lat"], c["lon"]) >= ecart for c in out):
                out.append({"h3": self.h3[i], "lat": la, "lon": lo, "score": round(float(score[i]), 4)})
                if len(out) >= n:
                    break
        return out


def proche(site, liste, km):
    return any(haversine(site["lat"], site["lon"], c["lat"], c["lon"]) <= km for c in liste)


# ---------------------------------------------------------------------- engine (in-process, read only)
def en_json(x):
    """The engine's answer as the API would send it (numpy values to plain JSON)."""
    conv = lambda o: o.item() if isinstance(o, np.generic) else o.tolist() if isinstance(o, np.ndarray) else str(o)
    return json.loads(json.dumps(x, default=conv))


def recherche(body, cells):
    """POST /api/search as the app sends it: default weights, dense vegetation <= 30%."""
    return en_json(combine.search(body, cells, None, None, None, {"max_vegetation": VEGETATION_MAX}, 2000))


def recherche_http(api, body, cells):
    return appel(f"{api}/api/search", {"body": body, "h3_cells": cells, "top_k": 2000,
                                       "filters": {"max_vegetation": VEGETATION_MAX}})


def _rang(x, eligible, s):
    """1 + number of eligible cells strictly better than s."""
    return int(1 + np.count_nonzero(x[eligible] > s))


def classer_analogues(body, cells, analogs):
    """Rank of each analog among ALL eligible Earth cells, with the engine's own scoring (combine.py), no filter.
    Per analog: its cell and its 6 neighbors, the best one; whether it passes the gates as the interface applies them
    (no criterion below the Earth median); and its rank on the slope distribution alone (baseline)."""
    T = earth_mod.earth()
    refs, inactive, _, _ = combine.references(body, tuple(sorted(cells)), None)
    w = combine.normalized_weights([BY_KEY[c] for c in refs], {}, None)
    active = [c for c in sorted(refs, key=lambda c: -w[c]) if w[c] > 0]
    sims = combine.similarities(T, {c: refs[c] for c in active})
    score, confidence, medians = combine.combine(T, sims, w)
    eligible = np.isfinite(score) & (confidence >= combine.MIN_CONFIDENCE)
    misses = sum((np.nan_to_num(sims[k], nan=np.inf) < medians[k]).astype(np.int8) for k in active)
    gated = eligible & (misses == 0)
    slope = slope_ok = None
    if "topography" in refs:
        m = BY_KEY["topography"]
        e = m.distance(m.variables[0], refs["topography"], T.modules["topography"])
        if e is not None:
            slope = np.where(e[1], 1 - e[0], np.nan)
            slope_ok = np.isfinite(slope)
    out = []
    for a in analogs:
        idx = known_analogs.site_rows(T, a["lat"], a["lon"])
        e = {**a, "cells": len(idx)}
        ok = [i for i in idx if eligible[i]]
        if ok:
            b = max(ok, key=lambda i: score[i])
            e.update(h3=T.h3(b), score=round(float(score[b]), 4), rank=_rang(score, eligible, score[b]),
                     passes_gates=bool(any(gated[i] for i in idx)),
                     per_module={k: None if not np.isfinite(sims[k][b]) else round(float(sims[k][b]), 3)
                                 for k in active},
                     below_median=[k for k in active if np.isfinite(sims[k][b]) and sims[k][b] < medians[k]])
        if slope is not None:
            s_ok = [i for i in idx if slope_ok[i]]
            if s_ok:
                bs = max(s_ok, key=lambda i: slope[i])
                e.update(rank_slope=_rang(slope, slope_ok, slope[bs]))
        out.append(e)
    return {"n_land": int(len(T.cells)), "n_eligible": int(eligible.sum()), "n_gated": int(gated.sum()),
            "n_slope": int(slope_ok.sum()) if slope_ok is not None else None, "analogs": out}


def couverture(cells):
    """Dense vegetation, urban and cloud cover (shares 0 to 1) of Earth cells, from the app's own tables."""
    T = earth_mod.earth()
    out = {}
    for c in cells:
        i = T.index(c)
        out[c] = {k: None if i is None or not np.isfinite(T.filters[k][i]) else round(float(T.filters[k][i]), 3)
                  for k in ("vegetation", "urban") if k in T.filters}
    f = db.parquet_path("thermal_light_extrems", "illumination", "earth")
    if f.is_file() and cells:
        d = db.read(f, ["cloud_fraction_mean"], cells)
        for h, v in zip(d["h3"], d["cloud_fraction_mean"]):
            if h in out:
                out[h]["cloud"] = None if not np.isfinite(v) else round(float(v), 3)
    return out


# ---------------------------------------------------------------------- run


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prod", default=None, help="deployed API, timed with the same base areas (optional)")
    a = p.parse_args()
    rng = random.Random(42)
    print("loading the Earth tables...", flush=True)
    earth_mod.earth()
    modules = [dict(m.description(), available={b: m.available(b) for b in m.bodies}) for m in MODULES]
    temps = []                       # engine time of every local search (s)
    sortie = {"areas": [], "variants": [], "stability": [], "coverage": [], "large": None}

    for A in AREAS:
        cells = zone(A)
        print(f"{A['name']}: {len(cells)} cells", flush=True)
        R = recherche(A["body"], cells)
        temps.append(R["duration_s"])
        res = Reserve(R)
        base = res.top()
        sites = [dict(x) for x in base]
        # backtest against all cells
        cat = [x for x in R["known"]] + [x for x in EXTRA]
        analogs = [{"id": x["id"], "name": x["name"], "lat": x["lat"], "lon": x["lon"]} for x in cat
                   if x["id"] in A["expected"] + A.get("minerals", [])]
        V = classer_analogues(A["body"], cells, analogs)
        lignes = []
        for x in V["analogs"]:
            src = next(c for c in cat if c["id"] == x["id"])
            e = {"id": x["id"], "name": x["name"], "source": src.get("source"), "expected": x["id"] in A["expected"],
                 "minerals": x["id"] in A.get("minerals", []), "cells": x["cells"]}
            if "rank" in x:
                e.update(rank=x["rank"], n=V["n_eligible"], pct=x["rank"] / V["n_eligible"],
                         passes_gates=x["passes_gates"], below_median=x["below_median"], per_module=x["per_module"],
                         in_top10=proche({"lat": x["lat"], "lon": x["lon"]}, base, 100))
            if "rank_slope" in x:
                e.update(rank_slope=x["rank_slope"], n_slope=V["n_slope"], pct_slope=x["rank_slope"] / V["n_slope"])
            c = max(1, x["cells"])
            e.update(pct_random=1 / (c + 1), p_top5_random=1 - 0.95 ** c)
            lignes.append(e)
        # worked example: detail of the #1 site
        exemple = None
        if base:
            exemple = en_json(combine.detail(A["body"], cells, base[0]["h3"]))["modules"]
        sortie["areas"].append({
            "id": A["id"], "body": A["body"], "name": A["name"], "lat": A["lat"], "lon": A["lon"], "radius_km": A["km"],
            "rings": anneaux(A["km"], A["body"]), "cells": len(cells), "area_km2": R["footprint"]["zone_area_km2"], "footprint": R["footprint"],
            "active": R["active_modules"], "inactive": R["inactive_modules"], "weights": R["weights"],
            "medians": R["medians"], "funnel": [{k: s.get(k) for k in ("stage", "module", "cells_remaining", "message")}
                                                for s in R["funnel"] if s["type"] == "progress"],
            "n_eligible": V["n_eligible"], "n_gated": V["n_gated"], "n_land": V["n_land"],
            "top10": sites, "analogs": lignes, "example": exemple, "duration_s": R["duration_s"]})

        # stability: weights × U(0.5, 1.5)
        top3 = base[:3]
        gardes, jacc = [], []
        for _ in range(RUNS):
            poids = {m: rng.uniform(0.5, 1.5) for m in res.actifs}
            t = res.top(poids)
            gardes.append(sum(proche(s, t, 30) for s in top3) / max(len(top3), 1))
            jacc.append(sum(proche(s, t, 30) for s in base) / max(len(base), 1))
        sortie["stability"].append({"id": A["id"], "top3_kept": statistics.mean(gardes),
                                    "all3_kept_runs": sum(g == 1 for g in gardes) / RUNS,
                                    "top10_overlap": statistics.mean(jacc), "runs": RUNS})

        # repainting
        for nom, fct, dec, al in VARIANTS:
            c2 = zone(A, fct, dec, al)
            R2 = recherche(A["body"], c2)
            temps.append(R2["duration_s"])
            r2 = Reserve(R2)
            t2 = r2.top()
            sortie["variants"].append({"id": A["id"], "variant": nom, "cells": len(c2), "n_pool": len(r2.h3),
                                       "gate_fails": r2.echecs, "medians": R2["medians"],
                                       "area_km2": R2["footprint"]["zone_area_km2"], "n_sites": len(t2),
                                       "top1_kept": bool(base) and proche(base[0], t2, 100),
                                       "top10_overlap": sum(proche(s, t2, 100) for s in base) / max(len(base), 1)})
        # coverage of the top 10
        if sites:
            cov = couverture([s["h3"] for s in sites])
            for s in sites:
                s.update(cov.get(s["h3"], {}))
        print(f"  done, {R['duration_s']} s", flush=True)

    # very large Moon area
    G = dict(next(x for x in AREAS if x["id"] == "mare"), km=GRAND["km"])
    cg = zone(G)
    try:
        Rg = recherche("moon", cg)
        temps.append(Rg["duration_s"])
        rg = Reserve(Rg)
        tg = rg.top()
        sortie["large"] = {"label": GRAND["label"], "cells": len(cg), "area_km2": Rg["footprint"]["zone_area_km2"],
                           "rings": Rg["footprint"]["rings"], "n_sites": len(tg), "n_pool": len(Rg["pool"]["h3"]),
                           "gate_fails": rg.echecs, "medians": Rg["medians"],
                           "n_best": Rg["n_best"], "funnel": [s.get("cells_remaining") for s in Rg["funnel"]
                                                              if s["type"] == "progress"]}
    except Exception as e:                                    # noqa: BLE001: reported on the page
        sortie["large"] = {"label": GRAND["label"], "cells": len(cg), "error": str(e)}

    # production timing (wall clock, network included)
    prod = []
    if a.prod:
        for A in AREAS:
            try:
                R, mur = recherche_http(a.prod, A["body"], zone(A))
                prod.append({"id": A["id"], "server_s": R["duration_s"], "wall_s": round(mur, 2)})
            except Exception as e:                            # noqa: BLE001
                prod.append({"id": A["id"], "error": str(e)})

    git = lambda *x: subprocess.run(["git", *x], cwd=RACINE, capture_output=True, text=True).stdout.strip()
    try:
        rel = subprocess.run(["gh", "release", "list", "--limit", "50", "--json", "tagName,createdAt"], cwd=RACINE,
                             capture_output=True, text=True, timeout=60)
        releases = json.loads(rel.stdout) if rel.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        releases = []
    dernieres = {}
    for r in sorted(releases, key=lambda r: r["createdAt"]):
        dernieres[r["tagName"].rsplit("-", 4)[0]] = r["tagName"]
    # data version: date of the newest output of each module (file dates only), and its release if published
    versions = {}
    for d in sorted((RACINE / "pretreatment_data").iterdir()):
        f = [x.stat().st_mtime for x in d.glob("*.parquet")]
        if f:
            versions[d.name] = {"date": dt.datetime.fromtimestamp(max(f)).strftime("%Y-%m-%d"),
                                "release": dernieres.get(d.name)}
    sortie.update({
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "commit": git("rev-parse", "--short", "HEAD"), "dirty": bool(git("status", "--porcelain")),
        "data_versions": versions, "modules": [{"key": m["key"], "name": m["name"], "available": m["available"]}
                                                for m in modules],
        "timing": {"local_server_s": temps, "local_median_s": statistics.median(temps), "prod": prod,
                   "prod_median_wall_s": statistics.median([x["wall_s"] for x in prod if "wall_s" in x])
                   if any("wall_s" in x for x in prod) else None,
                   "prod_median_server_s": statistics.median([x["server_s"] for x in prod if "server_s" in x])
                   if any("server_s" in x for x in prod) else None},
        "settings": {"spacing_km": ECART_KM, "vegetation_max": VEGETATION_MAX, "runs": RUNS, "weights": "all equal",
                     "seed": 42},
    })
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(json.dumps(sortie, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"written {SORTIE.relative_to(RACINE)}")


if __name__ == "__main__":
    main()
