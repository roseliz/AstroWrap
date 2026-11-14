// After npm install: sets up the application server (../server) in ../server/.venv
// and installs or updates its Python dependencies (requirements.txt).
// Never blocks npm install: if setup fails, a warning is displayed instead.
//
// À sauter : ANALOGUES_SANS_PYTHON=1 npm install.  Autre Python : ANALOGUES_PYTHON=chemin npm install.

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SERVEUR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "server");
const VENV = path.join(SERVEUR, ".venv");
const PY_VENV = process.platform === "win32" ? path.join(VENV, "Scripts", "python.exe") : path.join(VENV, "bin", "python");

function avis(texte) {
  console.log(`\n  [api] ${texte}\n`);
  process.exit(0);
}

if (process.env.ANALOGUES_SANS_PYTHON || process.env.CI) avis("Python setup skipped.");
if (!existsSync(path.join(SERVEUR, "requirements.txt"))) avis(`no server in ${SERVEUR}: nothing to install.`);

/** Premier Python 3.9+ du système (py -3 sous Windows, python3, python). */
function pythonSysteme() {
  const essais = [process.env.ANALOGUES_PYTHON && [process.env.ANALOGUES_PYTHON],
    process.platform === "win32" && ["py", "-3"], ["python3"], ["python"]].filter(Boolean);
  for (const [cmd, ...pre] of essais) {
    const r = spawnSync(cmd, [...pre, "-c", "import sys; print(sys.version_info >= (3, 9))"], { encoding: "utf8" });
    if (r.status === 0 && r.stdout.trim() === "True") return [cmd, pre];
  }
  return null;
}

if (!existsSync(PY_VENV)) {
  const py = pythonSysteme();
  if (!py) avis("no Python 3.9 or newer found: install it (python.org), then run npm install again.");
  console.log(`  [api] creating the Python environment: ${VENV}`);
  const r = spawnSync(py[0], [...py[1], "-m", "venv", VENV], { stdio: "inherit" });
  if (r.status !== 0) avis("could not create ../server/.venv; start the server by hand instead (see server/README.md).");
}

console.log("  [api] Python dependencies (server/requirements.txt), a few minutes the first time…");
const pip = spawnSync(PY_VENV, ["-m", "pip", "install", "--disable-pip-version-check", "-q", "-r",
  path.join(SERVEUR, "requirements.txt")], { stdio: "inherit" });
if (pip.status !== 0) avis("pip did not install everything (see above). The interface works; the server may be missing modules.");
console.log("  [api] ready.");
