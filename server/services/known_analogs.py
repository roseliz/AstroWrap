"""Known analogs: Earth sites that the literature compares with Mars or the Moon.

With each search, the footprint similarities of every known analog of the body, for its cell and its 6 neighbors,
in the same format as the pool. The browser scores them with the same weights, filters and funnel as the other
sites, and shows their actual rank. They never change the ranking itself.

scope: "environment" or "rocks" (what the tool compares); "mineralogy": analog of minerals or processes (acidic
sulfates, carbonates...), which the tool does not compare: its rank is shown but proves nothing.
"""

import h3
import numpy as np

from . import footprint, impact

CATALOG = [
    # --- Mars
    dict(id="devon", bodies=("mars",), name="Devon Island (Haughton crater)", country="Canada", lat=75.4, lon=-89.8,
         scope="environment", analog_of="cold polar desert and impact crater",
         source="Haughton-Mars Project (NASA); Lee and Osinski 2005"),
    dict(id="atacama", bodies=("mars",), name="Atacama Desert", country="Chile", lat=-24.5, lon=-69.25,
         scope="environment", analog_of="hyperarid desert, soils poor in organic matter",
         source="Navarro-González et al. 2003"),
    dict(id="dry_valleys", bodies=("mars", "moon"), name="McMurdo Dry Valleys", country="Antarctica",
         lat=-77.5, lon=162.0, scope="environment", analog_of="cold dry desert, frozen ground",
         source="Doran et al. 2010; polar analog of the Moon and Mars"),
    dict(id="mdrs", bodies=("mars",), name="Mars Desert Research Station", country="Utah, United States", lat=38.41,
         lon=-110.79, scope="environment", analog_of="sandstone and clay desert, simulated missions",
         source="Mars Society (MDRS station)"),
    dict(id="svalbard", bodies=("mars",), name="Bockfjorden (Svalbard)", country="Norway", lat=79.45, lon=13.3,
         scope="environment", analog_of="volcanoes and springs in an Arctic desert",
         source="AMASE expeditions (NASA, ESA)"),
    dict(id="rio_tinto", bodies=("mars",), name="Rio Tinto", country="Spain", lat=37.7, lon=-6.6,
         scope="mineralogy", analog_of="acidic sulfates and iron oxides of Meridiani",
         source="Fernández-Remolar et al. 2005"),
    dict(id="salda", bodies=("mars",), name="Lake Salda", country="Türkiye", lat=37.55, lon=29.68,
         scope="mineralogy", analog_of="carbonates and delta of Jezero crater", source="Horgan et al. 2020"),
    dict(id="oman", bodies=("mars",), name="Samail ophiolite", country="Oman", lat=23.0, lon=57.5,
         scope="mineralogy", analog_of="olivine altered to serpentine and carbonates (Nili Fossae)",
         source="serpentinization analog"),
    # --- Moon
    dict(id="kilauea", bodies=("moon",), name="Kilauea (Hawaii)", country="United States", lat=19.4, lon=-155.3,
         scope="environment", analog_of="basaltic maria, lava flows and lava tubes",
         source="lander and rover tests in Hawaii (PISCES)"),
    dict(id="meteor_crater", bodies=("moon",), name="Meteor Crater", country="Arizona, United States", lat=35.03,
         lon=-111.02, scope="environment", analog_of="simple impact crater and its ejecta",
         source="Apollo astronaut training"),
    dict(id="lanzarote", bodies=("moon",), name="Lanzarote (Timanfaya)", country="Spain", lat=29.0, lon=-13.75,
         scope="environment", analog_of="recent basaltic lava flows and cones",
         source="PANGAEA training (ESA)"),
    dict(id="adirondacks", bodies=("moon",), name="Adirondack anorthosites", country="New York, United States",
         lat=44.0, lon=-74.2, scope="rocks", analog_of="highland anorthosites",
         source="analog of the highland crust"),
]


def public(a: dict) -> dict:
    """What the interface receives about a known analog."""
    return {"id": a["id"], "name": a["name"], "country": a["country"], "lat": a["lat"], "lon": a["lon"],
            "scope": a["scope"], "analog_of": a["analog_of"], "source": a["source"]}


def site_rows(T, lat: float, lon: float):
    """Indices in T of the site's cell and of its neighbors (those on land)."""
    c = h3.latlng_to_cell(lat, lon, 5)
    idx = [T.index(x) for x in h3.grid_disk(c, 1)]
    return [i for i in idx if i is not None]


def _rounded(x, n):
    return [None if not np.isfinite(v) else round(float(v), n) for v in np.asarray(x, dtype=float)]


def for_search(T, body: str, refs: dict, active: list, k: int) -> list:
    """Known analogs of the body, in the pool format (one entry per analog, 7 cells at most)."""
    out = []
    for a in CATALOG:
        if body not in a["bodies"]:
            continue
        e = {**public(a), "h3": []}
        idx = site_rows(T, a["lat"], a["lon"])
        if idx:
            sims, rel, water, means = footprint.similarities(T, refs, active, np.array(idx), k, impact.extras(T))
            veg = T.filters.get("vegetation")
            prot = T.filters.get("protected")
            e.update({
                "h3": [T.h3(i) for i in idx],
                "score_per_module": {c: _rounded(sims[c], 3) for c in active},
                "reliability_per_module": {c: _rounded(rel[c], 2) for c in active},
                "water_share": _rounded(water, 3),
                "vegetation": _rounded(veg[idx], 3) if veg is not None else [None] * len(idx),
                "protected": _rounded(prot[idx], 3) if prot is not None else [None] * len(idx),
                "impact": impact.public(T, idx, means, lambda x, n: _rounded(x, n)),
            })
        out.append(e)
    return out
