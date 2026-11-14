"""Search: the reference area against the whole Earth, in one request (one to three seconds)."""

from fastapi import APIRouter, HTTPException

from ..schemas.search import DetailRequest, SearchRequest
from ..services import combine

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

