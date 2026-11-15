# Image of the FastAPI server. Build from server/:
#   docker build -t astrowrap-server .
# The data is not in the image: the machine syncs the module results (Parquet) from object storage to
# /data/app/pretreatment_data before starting the container (see deploy/).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ANALOGUES_DATA=/data/app/pretreatment_data \
    ANALOGUES_CACHE=/data/app/cache \
    ANALOGUES_DUCKDB_TEMP=/data/app/duckdb_tmp

# Code in /srv/server (the `server` package): config.ROOT (parents[2]) is then /srv
WORKDIR /srv

# libexpat1: needed by GDAL (rasterio wheel), missing from the slim image
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY . ./server

RUN useradd --uid 1000 --no-create-home server
USER server

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

# A single process: the Earth is kept in memory, and so are the areas sent by the interface (services/zones.py).
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
