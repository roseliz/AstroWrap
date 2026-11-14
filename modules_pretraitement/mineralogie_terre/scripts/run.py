"""Entry point of the mineralogie_terre module: runs one step, with the options of that step's script.

  python modules_pretraitement/mineralogie_terre/scripts/run.py <step> [options]

  catalog            CMR search of every EMIT L2B granule (~45 min, metadata only)        catalog.py
  selection          granules -> H3 cells, the 5 best per cell (arid zone, clouds <= 30 %) selection.py
  batch              process a list of granules (the worldwide run is done on AWS)        batch.py
  calibration-list   granules of the calibration zones                                     calibration_list.py
  calibration        calibration granules, then threshold report (the three steps above)
  merge              (default) per-granule counts -> pretreatment_data/mineralogie_terre/  merge.py
"""

from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path

from utils import CALIBRATION_DIR

HERE = Path(__file__).resolve().parent
STEPS = {"catalog": "catalog.py", "selection": "selection.py", "batch": "batch.py",
         "calibration-list": "calibration_list.py", "merge": "merge.py"}


def run_script(script: str, args: list[str]) -> None:
    """Run another script of the module in a separate process; stop on failure."""
    result = subprocess.run([sys.executable, str(HERE / script), *args])
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    step, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ("merge", [])
    if step in ("-h", "--help"):
        print(__doc__)
        return
    if step == "calibration":
        run_script("calibration_list.py", [])
        run_script("batch.py", ["--list", str(CALIBRATION_DIR / "liste.parquet"),
                                "--output", str(CALIBRATION_DIR / "granules_r7b"), "--resolution", "7", "--parallel", "8"])
        run_script("calibration.py", args)
        return
    if step not in STEPS:
        sys.exit(f"Unknown step: {step}\n{__doc__}")
    sys.argv = [str(HERE / STEPS[step]), *args]
    runpy.run_path(sys.argv[0], run_name="__main__")


if __name__ == "__main__":
    main()
