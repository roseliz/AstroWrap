"""Phase 0: catalog of the EMIT L2B MIN granules (CMR metadata only, nothing is downloaded).

For each granule: identifier, version, date, footprint (polygon), announced cloud cover, solar zenith angle,
URLs of the mineral file, of the uncertainty file and of the matching L2A mask, file sizes.
The CMR search is public: no Earthdata credentials are needed at this step.

Output: cache/mineralogie_terre/catalogue/granules_<version>.parquet (one file per version; the search is
saved month by month, so a new run resumes where it stopped).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd
import requests

from utils import CATALOG_DIR

CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
# Matching L2A mask: v001 -> collection EMITL2AMASK v002 (reprocessed masks, with SpecTf; the MASK file of the
# EMITL2ARFL v001 granule has no SpecTf); v002 -> collection EMITL2AMASK v003
DATA_URL = "https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected"


def mask_url(version: str, granule_ur: str) -> str:
    suffix = granule_ur.removeprefix(f"EMIT_L2B_MIN_{version}_")
    v = "002" if version == "001" else "003"
    g = f"EMIT_L2A_MASK_{v}_{suffix}"
    return f"{DATA_URL}/EMITL2AMASK.{v}/{g}/{g}.nc"


def catalog_row(version: str, item: dict) -> dict:
    """One catalog row from a CMR UMM-JSON granule item."""
    u = item["umm"]
    ur = u["GranuleUR"]
    links = [x["URL"] for x in u.get("RelatedUrls", []) if x.get("Type") == "GET DATA" and x["URL"].startswith("https")]
    sizes = {a["Name"]: a.get("SizeInBytes") for a in u.get("DataGranule", {}).get("ArchiveAndDistributionInformation", [])}
    attrs = {a["Name"]: a["Values"][0] for a in u.get("AdditionalAttributes", [])}
    polygon = u["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]["GPolygons"][0]["Boundary"]["Points"]
    # Test the FILE name: the granule folder is also called EMIT_L2B_MIN_..., including for MINUNCERT
    url_min = next((x for x in links if Path(x).name.startswith("EMIT_L2B_MIN_") and x.endswith(".nc")), None)
    url_unc = next((x for x in links if Path(x).name.startswith("EMIT_L2B_MINUNCERT_") and x.endswith(".nc")), None)
    name_min, name_unc = (Path(x).name if x else None for x in (url_min, url_unc))
    return {
        "granule": ur, "version": version,
        "debut": u["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"],
        "nuages": u.get("CloudCover"), "zenith_solaire": float(attrs.get("SOLAR_ZENITH", "nan")),
        "orbite": attrs.get("ORBIT"), "scene": attrs.get("SCENE"),
        "emprise": json.dumps([[p["Longitude"], p["Latitude"]] for p in polygon]),
        "url_min": url_min, "url_unc": url_unc, "url_masque": mask_url(version, ur),
        "octets_min": sizes.get(name_min), "octets_unc": sizes.get(name_unc),
    }


def search_month(session, version: str, start: str, end: str) -> list[dict]:
    """All EMIT L2B MIN granules of one version acquired between `start` and `end` (paged CMR search)."""
    params = {"short_name": "EMITL2BMIN", "version": version, "temporal": f"{start},{end}",
              "bounding_box": "-180,-54,180,54", "page_size": 2000}
    rows, search_after = [], None
    while True:
        headers = {"CMR-Search-After": search_after} if search_after else {}
        for attempt in range(5):
            r = session.get(CMR_URL, params=params, headers=headers, timeout=120)
            if r.ok:
                break
            time.sleep(5 * (attempt + 1))
        r.raise_for_status()
        items = r.json().get("items", [])
        rows += [catalog_row(version, it) for it in items]
        search_after = r.headers.get("CMR-Search-After")
        if not items or not search_after or len(items) < params["page_size"]:
            return rows


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--versions", nargs="+", default=["001", "002"], help="EMIT L2B versions (default: 001 002)")
    args = p.parse_args()
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    months = pd.date_range("2022-08-01", pd.Timestamp.today().normalize() + pd.offsets.MonthBegin(1), freq="MS")
    for v in args.versions:
        folder = CATALOG_DIR / f"mois_{v}"
        folder.mkdir(exist_ok=True)
        for start, end in zip(months[:-1], months[1:]):
            target = folder / f"{start:%Y-%m}.parquet"
            if target.exists():
                continue
            t0 = time.time()
            rows = search_month(session, v, f"{start:%Y-%m-%dT00:00:00Z}",
                                f"{end - pd.Timedelta(seconds=1):%Y-%m-%dT%H:%M:%SZ}")
            (pd.DataFrame(rows) if rows else pd.DataFrame(columns=["granule"])).to_parquet(target)
            print(f"v{v} {start:%Y-%m}: {len(rows):6d} granules ({time.time() - t0:.0f} s)", flush=True)
        t = pd.concat([pd.read_parquet(x) for x in sorted(folder.glob("*.parquet"))], ignore_index=True)
        t = t.dropna(subset=["granule"]).drop_duplicates("granule")
        t.to_parquet(CATALOG_DIR / f"granules_{v}.parquet")
        print(f"v{v}: {len(t):,} granules -> {CATALOG_DIR / f'granules_{v}.parquet'}", flush=True)


if __name__ == "__main__":
    main()
