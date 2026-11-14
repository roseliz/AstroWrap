"""Search: the reference area against the whole Earth, in one request (one to three seconds)."""

import re

from fastapi import APIRouter, HTTPException

from ..schemas.search import DetailRequest, SearchRequest, ZoneRequest
from ..services import combine, zones

router = APIRouter(prefix="/api", tags=["search"])


def _call(f, *a, **k):
    try:
        return f(*a, **k)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))


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

