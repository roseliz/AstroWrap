"""Card of an Earth site: what the six modules say about this cell, in readable units.

Reads one row per Earth file (DuckDB, ~30 ms); nothing is kept in memory.
"""

import math

import h3

from . import db, impact, places

K = 273.15

# (section, folder, table, suffix, [(column, label, conversion, unit)]); column names are those of the modules
CARD = [
    ("Climate", "thermal_light_extrems", "thermal", "", [
        ("air_temperature_mean", "Air temperature, mean", lambda v: v - K, "°C"),
        ("air_temperature_min", "Coldest month (air)", lambda v: v - K, "°C"),
        ("air_temperature_max", "Warmest month (air)", lambda v: v - K, "°C"),
        ("lst_day_max", "Hottest ground, by day", lambda v: v - K, "°C"),
        ("lst_night_min", "Coldest ground, at night", lambda v: v - K, "°C"),
    ]),
    ("Climate", "thermal_light_extrems", "illumination", "", [
        ("cloud_fraction_mean", "Cloud cover", lambda v: 100 * v, "%"),
        ("sunshine_duration_mean", "Sunshine", None, "h/day"),
    ]),
    ("Terrain", "topography_morphometry", "topography_morphometry", "_b500", [
        ("pente_p50", "Median slope", None, "°"),
        ("part_pente_inf_5", "Flat ground (< 5°)", lambda v: 100 * v, "%"),
        ("denivele_p5_p95", "Elevation range in the cell", None, "m"),
        ("densite_crateres", "Impact craters", None, "per 1,000 km²"),
    ]),
    ("Ground", "geology_mineralogy", "geology_mineralogy", "", [
        ("part_vegetation", "Dense vegetation", lambda v: 100 * v, "%"),
        ("part_artificiel", "Urban areas", lambda v: 100 * v, "%"),
        ("part_oxyde_fer", "Iron oxides (EMIT)", lambda v: 100 * v, "%"),
    ]),
    ("Wind", "wind_erosion_atmosphere", "wind_erosion_atmosphere", "", [
        ("part_dunes", "Dunes", lambda v: 100 * v, "%"),
        ("part_sol_nu", "Bare ground", lambda v: 100 * v, "%"),
        ("tempetes_freq", "Dust storms", lambda v: 100 * v, "% of days"),
    ]),
    ("Water and ice", "volatiles_hydrology_ice", "volatiles_hydrology_ice", "", [
        ("part_glace_surface", "Surface ice", lambda v: 100 * v, "%"),
        ("indice_glace_sol", "Permafrost", lambda v: 100 * v, "%"),
        ("humidite_sol", "Soil moisture", None, "m³/m³"),
        ("part_eau_libre", "Open water (lakes, rivers)", lambda v: 100 * v, "%"),
    ]),
    ("Caves and volcanoes", "astrobiology_habitability_caves", "astrobiology_habitability_caves", "", [
        ("n_volcans", "Volcanoes", None, ""),
        ("n_cavites", "Mapped caves", None, ""),
        ("n_tubes_lave", "Lava tubes", None, ""),
        ("n_sources_chaudes", "Hot springs", None, ""),
        ("part_karst", "Karst", lambda v: 100 * v, "%"),
        ("part_mine", "Mines", lambda v: 100 * v, "%"),
    ]),
    ("Field campaign", "environmental_impact", "environmental_impact", "", [
        ("part_protegee", "Protected area", lambda v: 100 * v, "%"),
        ("part_protegee_stricte", "Strictly protected (IUCN Ia, Ib, II)", lambda v: 100 * v, "%"),
    ]),
]
GROUPS = [("Rocks", "geology_mineralogy", "litho_"), ("Minerals (EMIT)", "geology_mineralogy", "comp_")]
# Class names used in the module's columns -> readable English names
CLASS_NAMES = {"basalte": "basalt", "volcanique_felsique": "felsic volcanic", "pyroclastique": "pyroclastic",
               "plutonique_basique": "mafic plutonic", "plutonique_felsique": "felsic plutonic",
               "sedimentaire_clastique": "clastic sedimentary", "non_consolide": "unconsolidated sediments",
               "carbonate": "carbonate", "evaporite": "evaporites", "metamorphique": "metamorphic", "glace": "ice",
               "impact": "impact", "pyroxene": "pyroxene", "olivine": "olivine", "feldspath": "feldspar",
               "mafique_autre": "other mafic", "argile_al": "Al clays", "argile_fe_mg": "Fe-Mg clays", "mica": "mica",
               "sulfate": "sulfates", "silice_hydratee": "hydrated silica", "sel": "salts", "autre_mineral": "other"}
ORDER = ["Climate", "Terrain", "Ground", "Wind", "Water and ice", "Caves and volcanoes", "Field campaign"]


def site_card(cell: str) -> dict:
    lat, lon = h3.cell_to_latlng(cell)
    sections = {}
    for section, folder, table, suffix, items in CARD:
        f = db.parquet_path(folder, table, "earth", suffix)
        if not f.is_file():
            continue
        present = set(db.columns(f))
        names = [c for c, *_ in items if c in present]
        if not names:
            continue
        d = db.read(f, names, [cell])
        if not len(d["h3"]):
            continue
        for c, label, conv, unit in items:
            if c not in d:
                continue
            v = float(d[c][0])
            if not math.isfinite(v):
                continue
            v = conv(v) if conv else v
            sections.setdefault(section, []).append({"label": label, "value": round(v, 2 if abs(v) < 10 else 1),
                                                     "unit": unit})
    for section, folder, prefix in GROUPS:
        f = db.parquet_path(folder, folder, "earth")
        if not f.is_file():
            continue
        cols = [c for c in db.columns(f) if c.startswith(prefix)]
        d = db.read(f, cols, [cell])
        if not len(d["h3"]):
            continue
        shares = sorted(((float(d[c][0]), c[len(prefix):]) for c in cols if math.isfinite(float(d[c][0]))), reverse=True)
        text = [f"{CLASS_NAMES.get(n, n.replace('_', ' '))} {round(100 * v)}%" for v, n in shares if v >= 0.05][:3]
        if text:
            sections.setdefault("Ground", []).insert(0, {"label": section, "value": ", ".join(text), "unit": ""})
    airport, sources = nearest_airport(cell)
    if airport:
        sections.setdefault("Field campaign", []).append(airport)
    return {
        "h3": cell,
        "lat": round(lat, 4),
        "lon": round(lon, 4),
        "area_km2": round(h3.cell_area(cell, "km^2"), 1),
        "place": places.place(lat, lon),
        "sections": [{"name": s, "items": sections[s]} for s in ORDER if s in sections],
        "sources": sources,
    }


def nearest_airport(cell: str):
    """("nearest airport" row of the card, sources to cite); (None, {}) without the impact module."""
    f = impact.parquet_file()
    if not f.is_file():
        return None, {}
    present = set(db.columns(f))
    src = impact.sources(f)
    sources = {"protected_areas": impact.citation(src)} if src.get("aires_protegees") else {}
    if not {"aeroport_nom", "aeroport_code", "distance_aeroport_km"} <= present:
        return None, sources
    r = db.cursor().execute("SELECT aeroport_nom, aeroport_code, distance_aeroport_km FROM read_parquet(?) WHERE h3 = ?",
                            [str(f), cell]).fetchone()
    if not r or r[2] is None or not math.isfinite(r[2]):
        return None, sources
    sources["airports"] = "OurAirports (public domain)"
    return {"label": "Nearest airport with scheduled flights", "value": f"{r[0]} ({r[1]}), {round(r[2]):,} km",
            "unit": ""}, sources
