// After npm install: creates server/.venv for the application server
// and installs or updates its Python dependencies (server/requirements.txt).
// Never makes npm install fail: if setup fails, a warning is printed instead.
//
// Skip it: ANALOGUES_SANS_PYTHON=1 npm install.  Other Python: ANALOGUES_PYTHON=path npm install.

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SERVEUR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "server");
const VENV = path.join(SERVEUR, ".venv");
const PY_VENV = process.platform === "win32" ? path.join(VENV, "Scripts", "python.exe") : path.join(VENV, "bin", "python");

function notice(text) {
  console.log(`\n  [api] ${text}\n`);
  process.exit(0);
}

if (process.env.ANALOGUES_SANS_PYTHON || process.env.CI) notice("Python setup skipped.");
if (!existsSync(path.join(SERVEUR, "requirements.txt"))) notice(`no server in ${SERVEUR}: nothing to install.`);

/** First Python 3.9 to 3.12 on the system (ANALOGUES_PYTHON, py -3 on Windows, python3, python). */
function pythonSysteme() {
  const essais = [process.env.ANALOGUES_PYTHON && [process.env.ANALOGUES_PYTHON],
    process.platform === "win32" && ["py", "-3"], ["python3"], ["python"]].filter(Boolean);
  for (const [cmd, ...pre] of essais) {
    const r = spawnSync(cmd, [...pre, "-c", "import sys; print((3, 9) <= sys.version_info[:2] <= (3, 12))"], { encoding: "utf8" });
    if (r.status === 0 && r.stdout.trim() === "True") return [cmd, pre];
  }
  return null;
}

if (!existsSync(PY_VENV)) {
  const py = pythonSysteme();
  if (!py) notice("no Python 3.9 to 3.12 found: install one (python.org), then run npm install again.");
  console.log(`  [api] creating the Python environment: ${VENV}`);
  const r = spawnSync(py[0], [...py[1], "-m", "venv", VENV], { stdio: "inherit" });
  if (r.status !== 0) notice("could not create server/.venv; start the server by hand instead (see server/README.md).");
}

console.log("  [api] Python dependencies (server/requirements.txt), a few minutes the first time…");
const pip = spawnSync(PY_VENV, ["-m", "pip", "install", "--disable-pip-version-check", "-q", "-r",
  path.join(SERVEUR, "requirements.txt")], { stdio: "inherit" });
if (pip.status !== 0) notice("pip did not install everything (see above). The interface works; the server may be missing modules.");
console.log("  [api] ready.");
