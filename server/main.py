"""Entry point: `uvicorn main:app` from server/, or `uvicorn server.main:app` from the repository root.

FastAPI, read-only over pretreatment_data/. The Earth is read in the background at startup (~15 s);
GET /api/health tells when it is ready.
"""

if not __package__:
    # Started as `uvicorn main:app` from server/: load the rest of the package as `server`.
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "server"

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .core import config
from .routes import meta, search
from .services import earth, places


@asynccontextmanager
async def lifespan(app):
    earth.start()
    places.load_in_background()      # place names (Natural Earth), downloaded once into cache/
    yield


app = FastAPI(title="AstroWrap: terrestrial analogs", version="1.0.0", lifespan=lifespan,
              description="Compares an area of Mars or the Moon with every H3 cell of the Earth.")
# Locally, the interface opens with a double click (origin "null"): every origin by default.
# Online: ANALOGUES_CORS=https://site-domain
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=2000)
app.include_router(meta.router)
app.include_router(search.router)
