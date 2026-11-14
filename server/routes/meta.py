"""Metadata: health, modules, presets."""

from fastapi import APIRouter

from ..core import config
from ..services import earth
from ..services.scoring.registry import MODULES

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def health():
    return {"ok": True, "data": str(config.DATA_DIR), "earth": earth.status()}


@router.get("/modules")
def modules():
    return {"modules": [dict(m.description(), available={b: m.available(b) for b in m.bodies}) for m in MODULES]}


@router.get("/presets")
def presets():
    return {"presets": [{"key": k, "name": p["name"],
                         "weights": {m.key: p["weights"].get(m.key, m.default_weight) for m in MODULES}}
                        for k, p in config.PRESETS.items()]}
