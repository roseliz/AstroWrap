from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .core import config
from .routes import meta, search
from .services import lieux, terre


@asynccontextmanager
async def lifespan(app):
    terre.demarrer()
    lieux.charger_en_fond()
    yield

    
app = FastAPI(title="Terrestrial Analogs", version="0.2.0", lifespan=lifespan,
              description="Compares an area of Mars or the Moon with every H3 cell of the Earth.")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINES, allow_methods=["GET", "POST"],
                   allow_headers=["*"])
app.add_middleware(GZipMiddleware, minimum_size=2000)
app.include_router(meta.routeur)
app.include_router(search.routeur)