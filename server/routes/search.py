"""Search: the reference area against the whole Earth, in one request (one to three seconds)."""

import re

import h3
from fastapi import APIRouter, HTTPException

from ..schemas.search import DetailRequest, NamesRequest, SearchRequest, ZoneRequest
from ..services import combine, places, relief, site_card, zones

router = APIRouter(prefix="/api", tags=["search"])


def _call(f, *a, **k):
    try:
        return f(*a, **k)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))


def _valid_cell(cell: str) -> str:
    if not h3.is_valid_cell(cell):
        raise HTTPException(status_code=422, detail=f"invalid H3 cell: {cell}")
    return cell


@router.post("/search")
def search(r: SearchRequest):
    return _call(combine.search, r.body, r.h3_cells, r.weights, r.preset, r.modules, r.filters.model_dump(), r.top_k)


@router.post("/search/detail")
def detail(r: DetailRequest):
    return _call(combine.detail, r.body, r.h3_cells, r.cell, r.modules)


@router.post("/zones")
def save_zone(r: ZoneRequest):
    """Saves a reference area; the interface only puts its identifier in the address."""
    return {"id": _call(zones.save, r.body, r.h3_cells)}


@router.get("/zones/{ident}")
def get_zone(ident: str):
    z = zones.load(ident) if re.fullmatch(r"[0-9a-f]{12}", ident) else None
    if z is None:
        raise HTTPException(status_code=404, detail="unknown area")
    return z


@router.get("/site/{cell}")
def site(cell: str):
    """Card of an Earth cell: place name (Natural Earth, OpenStreetMap) and module values."""
    return _call(site_card.site_card, _valid_cell(cell))


@router.post("/names")
def names(r: NamesRequest):
    """Quick place names of many Earth cells (Natural Earth regions and countries, no online lookup): the interface
    names its list of sites at once, then GET /api/site gives the full card of the site that is opened."""
    out = {}
    for c in r.cells:
        p = places.place(*h3.cell_to_latlng(_valid_cell(c)), online=False)
        out[c] = {"name": p["name"], "country": p["country"],
                  "kind": "region" if p["natural_regions"] else "country" if p["country"] else None}
    return {"names": out}


@router.get("/relief")
def terrain(body: str, lat: float, lon: float, size_km: float = 150, n: int = 256):
    """Terrain and imagery of a `size_km` square centered on (lat, lon), for the side-by-side 3D view (cache/relief/)."""
    if not (5 <= size_km <= 1000) or not (32 <= n <= 512):
        raise HTTPException(status_code=422, detail="size_km between 5 and 1000, n between 32 and 512")
    return _call(relief.relief, body.lower(), lat, lon, size_km, n)
