"""Pydantic DTOs of the search."""

from typing import Annotated, Dict, List, Optional

from pydantic import AfterValidator, BaseModel, Field, field_validator

from ..core import config

BODIES = ("mars", "moon")


def known_body(v: str) -> str:
    v = v.lower()
    if v not in BODIES:
        raise ValueError("body must be mars or moon")
    return v


def not_empty(v):
    if not v:
        raise ValueError("empty area")
    return v


Body = Annotated[str, AfterValidator(known_body)]
Cells = Annotated[List[str], AfterValidator(not_empty)]


class Filters(BaseModel):
    max_vegetation: Optional[float] = Field(None, ge=0, le=1, description="maximum share of dense vegetation")
    max_urban: Optional[float] = Field(None, ge=0, le=1, description="maximum share of urban areas")


class SearchRequest(BaseModel):
    body: Body = Field(description="body of the reference area: mars or moon; the search runs over the Earth")
    h3_cells: Cells = Field(description="H3 cells of the area, compacted or not (resolution 6, as in the interface)")
    preset: Optional[str] = Field(None, description="weight preset (GET /api/presets)")
    modules: Optional[List[str]] = Field(None, description="modules to use (default: all those with data)")
    weights: Dict[str, float] = Field(default_factory=dict, description="weight per module, normalized by the server")
    filters: Filters = Field(default_factory=Filters)
    top_k: int = Field(config.TOP_K_DEFAULT, ge=1, le=config.TOP_K_MAX)

    @field_validator("preset")
    @classmethod
    def known_preset(cls, v):
        if v is not None and v not in config.PRESETS:
            raise ValueError(f"unknown preset: {v}")
        return v


class DetailRequest(BaseModel):
    body: Body
    h3_cells: Cells
    cell: str = Field(description="Earth cell (resolution 5)")
    modules: Optional[List[str]] = None


class ZoneRequest(BaseModel):
    body: Body
    h3_cells: Cells = Field(description="H3 cells of the area, compacted or not (resolution 6, as in the interface)")


class NamesRequest(BaseModel):
    cells: List[str] = Field(max_length=100, description="Earth cells (resolution 5) to name, at most 100")
