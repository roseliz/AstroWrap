"""Process a list of granules: download into a temporary folder, count per H3 cell, delete.

Two small Parquet files per granule; a granule already done is skipped (resume after a stop or a Spot
interruption). Several machines can process the same list: each one goes through it in its own random order
(--shuffle) and checks, right before each granule, that no other machine has written it yet. A duplicate
(two machines at the same time) rewrites the same file identically.

  python batch.py --list <parquet> --output <folder or s3://bucket/prefix> [--source https|s3] [--production]

  --source https  (default) from anywhere, Earthdata credentials in the environment or .env
  --source s3     direct reads from the NASA buckets: only from the AWS us-west-2 region; temporary S3
                  tokens (1 h) renewed every 50 min
  --production    lighter output (mask and thresholds of thresholds.py applied, snr classes kept)
  --ssm <prefix>  read the Earthdata credentials from AWS SSM (<prefix>username, <prefix>password)
  --shuffle       random order specific to each run (several machines on the same list)

Exit code: 0 the whole list is done; 3 only granules that failed on this machine are missing;
4 others are missing (still running on another machine, or failed elsewhere).

List: Parquet with granule, version, url_min, url_unc, url_masque. Log: <output>/_journal/<granule>.json.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from granule import MASKS, process_local, reduce_for_production
from thresholds import thresholds_table
from utils import earthdata_login

NASA_BUCKET = "lp-prod-protected"


def load_ssm_credentials(prefix: str, region: str) -> None:
    """Earthdata credentials from AWS SSM (SecureString), placed in this process's environment only."""
    import boto3
    r = boto3.client("ssm", region_name=region).get_parameters(
        Names=[prefix + "username", prefix + "password"], WithDecryption=True)
    v = {p["Name"].removeprefix(prefix): p["Value"] for p in r["Parameters"]}
    if set(v) != {"username", "password"}:
        sys.exit(f"SSM parameters {prefix}* not found")
    os.environ["EARTHDATA_USERNAME"], os.environ["EARTHDATA_PASSWORD"] = v["username"], v["password"]


# ------------------------------------------------------------------ sources
class HttpsSource:
    """Download through the Earthdata HTTPS session (works from anywhere)."""

    def __init__(self, ea):
        self.session = ea.get_requests_https_session()

    def download(self, url: str, target: Path) -> int:
        for attempt in range(4):
            try:
                n = 0
                with self.session.get(url, stream=True, timeout=300) as r:
                    r.raise_for_status()
                    with open(target, "wb") as f:
                        for chunk in r.iter_content(8 * 2**20):
                            f.write(chunk)
                            n += len(chunk)
                return n
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(10 * (attempt + 1))
        return 0


class S3Source:
    """Direct reads from the LP DAAC bucket. The tokens last 1 h: renewed every 50 min."""

    def __init__(self, ea, region: str = "us-west-2"):
        self.ea, self.region = ea, region
        self.lock = threading.Lock()
        self.client, self.created = None, 0.0

    def _client(self):
        import boto3
        with self.lock:
            if self.client is None or time.time() - self.created > 50 * 60:
                token = self.ea.get_s3_credentials(daac="LPDAAC")
                self.client = boto3.client("s3", region_name=self.region, aws_access_key_id=token["accessKeyId"],
                                           aws_secret_access_key=token["secretAccessKey"],
                                           aws_session_token=token["sessionToken"])
                self.created = time.time()
            return self.client

    def download(self, url: str, target: Path) -> int:
        key = url.split(f"/{NASA_BUCKET}/", 1)[1]
        for attempt in range(4):
            try:
                self._client().download_file(NASA_BUCKET, key, str(target))
                return target.stat().st_size
            except Exception:
                if attempt == 3:
                    raise
                with self.lock:
                    self.client = None                     # the token may have expired: ask for a new one
                time.sleep(5 * (attempt + 1))
        return 0


# ------------------------------------------------------------------ outputs
class Output:
    """Local folder or s3://bucket/prefix (permissions come from the machine's role)."""

    def __init__(self, target: str, region: str = "us-west-2"):
        self.s3 = target.startswith("s3://")
        if self.s3:
            import boto3
            self.bucket, _, self.prefix = target[5:].partition("/")
            self.prefix = self.prefix.rstrip("/")
            self.client = boto3.client("s3", region_name=region)
        else:
            self.folder = Path(target)
            (self.folder / "_journal").mkdir(parents=True, exist_ok=True)

    def done_granules(self) -> set[str]:
        """Granules whose two files already exist (a single listing at start-up)."""
        if self.s3:
            names = set()
            for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=self.prefix + "/"):
                names |= {o["Key"].rsplit("/", 1)[-1] for o in page.get("Contents", [])}
        else:
            names = {p.name for p in self.folder.glob("*.parquet")}
        return {n.removesuffix("_histo.parquet") for n in names if n.endswith("_histo.parquet")
                and n.replace("_histo.parquet", "_cellules.parquet") in names}

    def is_done(self, granule: str) -> bool:
        """Is the granule already written (by this machine or another)? The cells file is written last."""
        name = f"{granule}_cellules.parquet"
        if not self.s3:
            return (self.folder / name).exists()
        try:
            self.client.head_object(Bucket=self.bucket, Key=f"{self.prefix}/{name}")
            return True
        except self.client.exceptions.ClientError:
            return False

    def write(self, name: str, t: pd.DataFrame) -> None:
        if self.s3:
            b = io.BytesIO()
            t.to_parquet(b, index=False)
            self.client.put_object(Bucket=self.bucket, Key=f"{self.prefix}/{name}", Body=b.getvalue())
        else:
            t.to_parquet(self.folder / name, index=False)

    def log(self, granule: str, info: dict) -> None:
        text = json.dumps(info, ensure_ascii=False)
        if self.s3:
            self.client.put_object(Bucket=self.bucket, Key=f"{self.prefix}/_journal/{granule}.json", Body=text.encode())
        else:
            (self.folder / "_journal" / f"{granule}.json").write_text(text, encoding="utf-8")


# ------------------------------------------------------------------ processing
def production_settings() -> dict:
    """Mask bits and minimum weight / fit of the frozen thresholds (thresholds.py)."""
    s = thresholds_table()
    masks = s["masque"].unique()
    if len(masks) != 1:
        raise ValueError("thresholds.py: a single mask is expected")
    return {"bits": MASKS[masks[0]], "min_weight": float(s["poids_min"].min()), "min_fit": float(s["fit_min"].min())}


def process_granule(source, output: Output, g, resolution: int, production: dict | None, tmp_root: str | None) -> str:
    """Download, count and write one granule; returns a short status string."""
    if output.is_done(g.granule):                   # written meanwhile by another machine
        return "ALREADY DONE"
    tmp = Path(tempfile.mkdtemp(prefix="emit_", dir=tmp_root))
    info = {"granule": g.granule, "octets": 0, "s_telechargement": 0.0, "s_lecture": 0.0, "s_calcul": 0.0, "erreur": ""}
    try:
        t = time.time()
        paths = []
        for url in (g.url_min, g.url_unc, g.url_masque):
            p = tmp / url.rsplit("/", 1)[-1]
            info["octets"] += source.download(url, p)
            paths.append(p)
        info["s_telechargement"] = time.time() - t
        cells, histo, timings = process_local(*paths, granule=g.granule, version=g.version, resolution=resolution)
        if production:
            cells, histo = reduce_for_production(cells, histo, production["bits"], production["min_weight"],
                                                 production["min_fit"])
        info.update(timings)
        # histo first, cells last: a granule is only "done" when both exist
        output.write(f"{g.granule}_histo.parquet", histo)
        output.write(f"{g.granule}_cellules.parquet", cells)
        return f"{len(cells)} cells"
    except Exception as e:
        info["erreur"] = f"{type(e).__name__}: {e}"[:300]
        return "ERROR " + info["erreur"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            output.log(g.granule, info)
        except Exception:
            pass


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list", required=True, help="local Parquet file or s3://...")
    p.add_argument("--output", required=True, help="local folder or s3://bucket/prefix")
    p.add_argument("--source", choices=["https", "s3"], default="https")
    p.add_argument("--parallel", type=int, default=4, help="granules processed at the same time (default: 4)")
    p.add_argument("--resolution", type=int, default=5, help="H3 resolution (default: 5)")
    p.add_argument("--production", action="store_true")
    p.add_argument("--ssm", help="prefix of the SSM parameters holding the Earthdata credentials")
    p.add_argument("--region", default="us-west-2")
    p.add_argument("--tmp", help="folder for the temporary files")
    p.add_argument("--max", type=int, default=0, help="only process N granules (test)")
    p.add_argument("--shuffle", action="store_true", help="random order (several machines)")
    args = p.parse_args()
    if args.ssm:
        load_ssm_credentials(args.ssm, args.region)
    ea = earthdata_login()
    source = S3Source(ea, args.region) if args.source == "s3" else HttpsSource(ea)
    output = Output(args.output, args.region)
    granules = pd.read_parquet(args.list)
    if args.max:
        granules = granules.head(args.max)
    done = output.done_granules()
    todo = granules[~granules.granule.isin(done)]
    if args.shuffle:
        todo = todo.sample(frac=1, random_state=int.from_bytes(os.urandom(4), "little"))
    print(f"{len(granules)} granules, {len(granules) - len(todo)} already done, {len(todo)} to process", flush=True)
    production = production_settings() if args.production else None
    t0, n, already, failed = time.time(), 0, 0, set()
    with ThreadPoolExecutor(args.parallel) as ex:
        futures = {ex.submit(process_granule, source, output, g, args.resolution, production, args.tmp): g.granule
                   for g in todo.itertuples()}
        for f in as_completed(futures):
            n += 1
            status = f.result()
            already += status == "ALREADY DONE"
            if status.startswith("ERROR"):
                failed.add(futures[f])
            print(f"[{n}/{len(todo)} {time.time() - t0:.0f} s] {futures[f]}: {status}", flush=True)
    missing = set(granules.granule) - output.done_granules()
    print(f"end: {n - already} processed, {already} already done elsewhere, {len(failed)} errors, "
          f"{time.time() - t0:.0f} s; {len(missing)} granules of the list still missing", flush=True)
    if not missing:
        return 0
    return 3 if missing <= failed else 4


if __name__ == "__main__":
    sys.exit(main())
