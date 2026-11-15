"""Module weighting, funnel, top-K and pool of cells for the interface.

Score of an Earth cell = Σ w × s / Σ w over the active modules, with:
- s: module similarity (0 to 1); without data on the cell (minerals under forest...), the module's median over the
  Earth: "unknown" makes the cell neither more nor less similar than average;
- w: module weight (normalized) × (0.5 + 0.5 × cell reliability), or × 1 without data.
confidence = share of the weight of the modules actually measured on the cell; a cell is only a candidate from
MIN_CONFIDENCE.

Funnel (shown step by step by the interface): start from the land cells, apply the filters (vegetation...), then
each module, from heaviest to lightest, counts a "miss" for the cells that look less like the area than the Earth's
median (a cell without data counts none). A cell is removed once it has more misses than MAX_BELOW_MEDIAN: one weak
point is forgiven (Rio Tinto, very close to Meridiani by its rocks, but hilly instead of flat), as long as at least
MODULES_TO_TOLERATE criteria are active (with one or two criteria, no miss is tolerated). The final ranking is made
among the survivors. The response has the shape of the
planned WebSocket events (progress, partial, done): the interface replays them.

Area against area (services/footprint.py): the pool sent to the browser is scored over the footprint of each cell
(a disk with the same area as the reference area), with its water share; so is the detail of a site.
"""

import math
import time
from functools import lru_cache

import h3
import numpy as np

from ..core import config
from . import earth as earth_mod
from . import footprint, impact, zones
from .scoring.registry import BY_KEY, for_body

MIN_CONFIDENCE = 0.6
MAX_BELOW_MEDIAN = 1         # criteria below the Earth's median that a cell may have without being removed
MODULES_TO_TOLERATE = 3      # below this number of active criteria, no miss is tolerated


def tolerated_misses(n_active: int) -> int:
    return MAX_BELOW_MEDIAN if n_active >= MODULES_TO_TOLERATE else 0


def normalized_weights(modules, weights: dict, preset):
    base = dict(config.PRESETS.get(preset, {}).get("weights", {})) if preset else {}
    base.update(weights or {})
    w = {m.key: max(0.0, float(base.get(m.key, m.default_weight))) for m in modules}
    total = sum(w.values())
    if total <= 0:
        raise ValueError("all weights are zero")
    return {k: v / total for k, v in w.items()}


@lru_cache(maxsize=32)
def references(body: str, cells: tuple, requested) -> tuple:
    """Reference of each module (cached: the same area comes back at each change of weights or detail)."""
    keys, weights = zones.to_resolution(list(cells))
    refs, inactive = {}, []
    modules = for_body(body, set(requested) if requested else None)
    for m in modules:
        r = m.reference(keys, weights, body)
        if r is None:
            inactive.append({"key": m.key, "reason": "no data on the area"})
        else:
            refs[m.key] = r
    missing = [{"key": m.key, "reason": f"no data for {body}"}
               for m in BY_KEY.values() if m not in modules and (not requested or m.key in requested)]
    return refs, inactive + missing, len(keys), float(np.sum(weights))


def similarities(T, refs: dict) -> dict:
    sims = {}
    for k, ref in refs.items():
        if k in T.modules:
            sims[k] = BY_KEY[k].score(ref, T.modules[k])
    return sims


def combine(T, sims: dict, w: dict):
    n = len(T.cells)
    total, weight, measured, w_total = np.zeros(n), np.zeros(n), np.zeros(n), 0.0
    medians = {}
    for k, s in sims.items():
        ok = np.isfinite(s)
        medians[k] = float(np.median(s[ok])) if ok.any() else 0.5
        r = T.modules[k].reliability
        we = w[k] * np.where(ok, 0.5 + 0.5 * np.nan_to_num(r, nan=1.0), 1.0)
        total += np.where(ok, s, medians[k]) * we
        weight += we
        measured += np.where(ok, w[k], 0.0)
        w_total += w[k]
    score = np.where(weight > 0, total / np.maximum(weight, 1e-12), np.nan)
    return score, measured / max(w_total, 1e-12), medians


def search(body, cells, weights=None, preset=None, modules=None, filters=None, top_k=None) -> dict:
    t0 = time.time()
    T = earth_mod.earth()
    refs, inactive, n_ref, tiles = references(body, tuple(sorted(cells)), tuple(sorted(modules)) if modules else None)
    if not refs:
        raise ValueError(f"no module has data on this area of {body}")
    w = normalized_weights([BY_KEY[c] for c in refs], weights or {}, preset)
    active = [c for c in sorted(refs, key=lambda c: -w[c]) if w[c] > 0]
    sims = similarities(T, {c: refs[c] for c in active})
    score, confidence, medians = combine(T, sims, w)
    top_k = min(top_k or config.TOP_K_DEFAULT, config.TOP_K_MAX)

    # ---------------------------------------------------------------- funnel
    filters = filters or {}
    events = []
    alive = np.isfinite(score) & (confidence > 0)
    n_steps = len(active) + 2
    events.append(step("start", None, 0, n_steps, int(alive.sum()), "Land cells"))
    keep = np.ones(len(T.cells), dtype=bool)
    for name, k in (("max_vegetation", "vegetation"), ("max_urban", "urban"), ("max_protected", "protected")):
        threshold = filters.get(name)
        if threshold is not None and k in T.filters:
            keep &= ~(T.filters[k] > threshold)         # without data: kept
    alive &= keep
    events.append(step("filters", None, 1, n_steps, int(alive.sum()), filters_message(filters)))
    last = np.where(np.isfinite(score) & (confidence > 0), 0, -1).astype(np.int8)   # last step survived
    last[alive] = 1
    partial_s, partial_w = np.zeros(len(T.cells)), np.zeros(len(T.cells))
    misses, allowed = np.zeros(len(T.cells), dtype=np.int8), tolerated_misses(len(active))
    for i, k in enumerate(active, start=2):
        s = sims[k]
        misses += (s < medians[k]).astype(np.int8)      # NaN (no data): no miss
        alive &= misses <= allowed
        last[alive] = i
        partial_s += np.where(np.isfinite(s), s, medians[k]) * w[k]
        partial_w += w[k]
        events.append(step("module", k, i, n_steps, int(alive.sum()), f"{BY_KEY[k].name}: {i - 1}/{len(active)}"))
        events.append({"type": "partial", "module": k,
                       "top": best(T, np.where(alive, partial_s / partial_w, -1), config.TOP_PER_STEP)})

    final = alive & (confidence >= MIN_CONFIDENCE)
    last[final] = n_steps
    ranking = np.where(final, score, -1.0)
    order = np.argsort(-ranking)
    order = order[ranking[order] >= 0][:top_k]

    # ---------------------------------------------------------------- pool for the browser
    eligible = keep & np.isfinite(score) & (confidence >= MIN_CONFIDENCE)
    pool = set(top_indices(np.where(eligible, score, -1), config.POOL_SIZE).tolist())
    for k in active:
        pool |= set(top_indices(np.where(eligible, np.nan_to_num(sims[k], nan=-1), -1), config.POOL_PER_MODULE).tolist())
    pool |= set(order.tolist())
    pool = np.array(sorted(pool, key=lambda i: -score[i]), dtype=np.int64)

    # ---------------------------------------------------------------- area against area
    k = footprint.rings(tiles, body)
    sims_f, rel_f, water, means_f = footprint.similarities(T, refs, active, pool, k, impact.extras(T))
    measured_f = sum(np.where(np.isfinite(sims_f[c]), w[c], 0.0) for c in active) / max(sum(w[c] for c in active), 1e-12)

    from . import known_analogs                       # imported here: known_analogs imports this module
    known = known_analogs.for_search(T, body, refs, active, k)

    events.append({"type": "done", "cells_remaining": int(final.sum()), "message": "Ranking done"})
    return {
        "body": body,
        "n_cells_reference": n_ref,
        "n_cells_earth": int(np.isfinite(score).sum()),
        "active_modules": active,
        "inactive_modules": inactive + [{"key": c, "reason": "zero weight"} for c in refs if w[c] == 0],
        "weights": {c: round(w[c], 4) for c in active},
        "filters": filters,
        "medians": {c: round(medians[c], 4) for c in active},
        "confidence_min": MIN_CONFIDENCE,
        "max_below_median": allowed,
        "reference": {c: public_reference(c, refs[c]) for c in active},
        "funnel": events,
        "funnel_regions": funnel_regions(T, last),
        "best_cells": [cell_entry(T, i, score, confidence, sims) for i in order[:50]],
        "n_best": int(len(order)),
        "footprint": {"rings": k, "cells": 3 * k * k + 3 * k + 1,
                      "area_km2": round((3 * k * k + 3 * k + 1) * footprint.R5_AREA_KM2),
                      "zone_area_km2": round(footprint.zone_area_km2(tiles, body)), "max_water": footprint.MAX_WATER},
        "pool": {
            "h3": [T.h3(i) for i in pool],
            "confidence": rounded(measured_f, 3),
            "score_per_module": {c: rounded(sims_f[c], 3) for c in active},
            "reliability_per_module": {c: rounded(rel_f[c], 2) for c in active},
            "water_share": rounded(water, 3),
            "cell_score_per_module": {c: rounded(sims[c][pool], 3) for c in active},
            "impact": impact.public(T, pool, means_f, rounded),
        },
        "known": known,
        "duration_s": round(time.time() - t0, 2),
    }


def detail(body, cells, earth_cell, modules=None) -> dict:
    """Values of the area and of the Earth cell, variable by variable (detail panel)."""
    T = earth_mod.earth()
    i = T.index(earth_cell)
    if i is None:
        raise ValueError(f"unknown Earth cell: {earth_cell}")
    refs, _, _, tiles = references(body, tuple(sorted(cells)), tuple(sorted(modules)) if modules else None)
    k = footprint.rings(tiles, body)
    idx = footprint.neighbors(T, [i], k)
    out = []
    for key, ref in refs.items():
        m, D0 = BY_KEY[key], T.modules.get(key)
        if D0 is None:
            continue
        D = footprint.footprint_data(D0, idx)            # mean over the site's footprint (row 0)
        s = m.score(ref, D)[0]
        variables = []
        for v in m.variables:
            if v.key not in ref["variables"]:
                continue
            x = D.values.get(v.key)
            e = m.distance(v, ref, D, slice(0, 1))
            sim = None if e is None or not e[1][0] else round(1 - float(e[0][0]), 3)
            variables.append({"key": v.key, "label": v.label, "mode": v.mode, "unit": v.unit,
                              "reference": public_value(v, ref["variables"][v.key]),
                              "earth": public_value(v, x[0]) if x is not None else None,
                              "similarity": sim, "compared": e is not None,
                              "range": [round(b, 3) for b in D0.bounds[v.key]] if v.key in D0.bounds else None})
        out.append({"key": key, "name": m.name, "similarity": None if not math.isfinite(s) else round(float(s), 3),
                    "reliability": as_float(D.reliability[0], 2), "variables": variables})
    cells_f = footprint.footprint_cells(earth_cell, k)
    return {"h3": earth_cell, "modules": out,
            "footprint": {"rings": k, "cells": cells_f, "water_share": round(float(footprint.water_share(idx, k)[0]), 3),
                          "area_km2": round(len(cells_f) * footprint.R5_AREA_KM2)}}


def funnel_regions(T, last):
    """For the animation: each resolution-3 cell and the last step where it still has a living cell
    (0 = land, 1 = filters, 2... = modules, total = final ranking)."""
    order = T.region_order
    parents, start = np.unique(T.region_parents[order], return_index=True)
    best_step = np.maximum.reduceat(last[order], start)
    keep = best_step >= 0
    return {"resolution": 3, "h3": [h3.int_to_str(int(c)) for c in parents[keep]],
            "last_step": best_step[keep].astype(int).tolist()}


# ---------------------------------------------------------------------- formatting
def step(stage, module, number, total, remaining, message):
    return {"type": "progress", "stage": stage, "module": module, "step": number, "total": total,
            "cells_remaining": remaining, "message": message}


def filters_message(f):
    p = []
    if f.get("max_vegetation") is not None:
        p.append(f"vegetation ≤ {round(100 * f['max_vegetation'])}%")
    if f.get("max_urban") is not None:
        p.append(f"urban areas ≤ {round(100 * f['max_urban'])}%")
    if f.get("max_protected") is not None:
        p.append(f"protected areas ≤ {round(100 * f['max_protected'])}%")
    return "Filters: " + ", ".join(p) if p else "No filter"


def top_indices(x, k):
    k = min(k, len(x))
    if k <= 0:
        return np.array([], dtype=np.int64)
    i = np.argpartition(-x, k - 1)[:k]
    return i[x[i] >= 0]


def best(T, x, k):
    i = top_indices(x, k)
    i = i[np.argsort(-x[i])]
    return [{"h3": T.h3(j), "score": round(float(x[j]), 3)} for j in i]


def as_float(x, n):
    return None if not np.isfinite(x) else round(float(x), n)


def rounded(x, n):
    a = np.round(np.asarray(x, dtype=np.float64), n).astype(object)
    a[~np.isfinite(np.asarray(x, dtype=np.float64))] = None
    return a.tolist()


def cell_entry(T, i, score, confidence, sims):
    return {"h3": T.h3(i), "score": round(float(score[i]), 4), "confidence": round(float(confidence[i]), 3),
            "score_per_module": {c: as_float(s[i], 3) for c, s in sims.items()},
            "reliability_per_module": {c: as_float(T.modules[c].reliability[i], 2) for c in sims}}


def public_value(v, x):
    if v.mode == "hellinger":
        x = np.asarray(x, dtype=float)
        return {c: round(float(a), 3) for c, a in zip(v.classes, x) if np.isfinite(a)}
    if v.mode == "deciles":
        return [as_float(a, 2) for a in np.asarray(x, dtype=float)]
    return as_float(x, 4)


def public_reference(key, ref):
    m = BY_KEY[key]
    return {"name": m.name, "reliability": None if ref["reliability"] is None else as_float(ref["reliability"], 3),
            "variables": [{"key": v.key, "label": v.label, "mode": v.mode, "unit": v.unit,
                           "value": public_value(v, ref["variables"][v.key])}
                          for v in m.variables if v.key in ref["variables"]]}
