// npm start: serves the frontend (http://localhost:8080) and starts the application server (FastAPI, port 8000).
//
//   npm start          Frontend + server
//   npm run client     Frontend only (the server is already running elsewhere: use ?api=… in the URL)
//   npm run api        Server only
//
// The server uses Python from ../server/.venv (created by npm install), then ANALOGUES_PYTHON
// if available, and finally the system Python as a fallback.
// If the server is already responding on port 8000, it will not be restarted.
//
// Environment variables: PORT (frontend, default 8080), API_PORT (server, default 8000).

import { spawn } from "node:child_process";
import { existsSync, createReadStream, statSync } from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const CLIENT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SERVEUR = path.resolve(CLIENT, "..", "server");
const PORT = Number(process.env.PORT || 8080);
const API_PORT = Number(process.env.API_PORT || 8000);
const args = new Set(process.argv.slice(2));
const AVEC_CLIENT = !args.has("--api-seule");
const AVEC_API = !args.has("--sans-api");

const TYPES = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".map": "application/json",
  ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
  ".ico": "image/x-icon", ".woff": "font/woff", ".woff2": "font/woff2", ".wasm": "application/wasm", ".md": "text/plain; charset=utf-8",
};

// ------------------------------------------------------------------ Frontend (static files)
function servirClient() {
  const serveur = http.createServer((req, res) => {
    let chemin;
    try {
      chemin = decodeURIComponent(new URL(req.url, "http://x").pathname);
    } catch {
      res.writeHead(400).end();
      return;
    }
    let fichier = path.normalize(path.join(CLIENT, chemin));
    if (fichier !== CLIENT && !fichier.startsWith(CLIENT + path.sep)) { res.writeHead(403).end(); return; }   // pas de ../
    if (existsSync(fichier) && statSync(fichier).isDirectory()) fichier = path.join(fichier, "index.html");
    if (!existsSync(fichier)) {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" }).end(`Introuvable : ${chemin}`);
      return;
    }
    res.writeHead(200, {
      "Content-Type": TYPES[path.extname(fichier).toLowerCase()] || "application/octet-stream",
      "Cache-Control": "no-cache",                     // en développement, toujours la dernière version
    });
    createReadStream(fichier).pipe(res);
  });
  serveur.on("error", (e) => {
    console.error(e.code === "EADDRINUSE"
      ? `Port ${PORT} is already in use. Try for example: PORT=8081 npm start (Windows: $env:PORT=8081; npm start)`
      : e.message);
    process.exit(1);
  });
  serveur.listen(PORT, () => {
    console.log(`\n  Terrestrial Analogs: http://localhost:${PORT}\n`);
  });
}

// ------------------------------------------------------------------ Application server (FastAPI)
function python() {
  const candidats = [
    process.env.ANALOGUES_PYTHON,
    path.join(SERVEUR, ".venv", "Scripts", "python.exe"),   // Windows
    path.join(SERVEUR, ".venv", "bin", "python"),            // Linux, macOS
  ].filter(Boolean);
  return candidats.find((p) => existsSync(p)) || (process.platform === "win32" ? "python" : "python3");
}

async function apiDejaLancee() {
  try {
    const r = await fetch(`http://127.0.0.1:${API_PORT}/api/health`, { signal: AbortSignal.timeout(1500) });
    return r.ok;
  } catch {
    return false;
  }
}

let api = null;
async function lancerApi() {
  if (await apiDejaLancee()) {
    console.log(`  [api] already running on http://127.0.0.1:${API_PORT}`);
    return;
  }
  const py = python();
  console.log(`  [api] ${py} -m uvicorn app.main:app --port ${API_PORT}`);
  api = spawn(py, ["-m", "uvicorn", "app.main:app", "--port", String(API_PORT)], { cwd: SERVEUR, env: process.env });
  const prefixer = (flux, sortie) => {
    let reste = "";
    flux.on("data", (morceau) => {
      const lignes = (reste + morceau).split(/\r?\n/);
      reste = lignes.pop();
      lignes.forEach((l) => sortie.write(`  [api] ${l}\n`));
    });
  };
  prefixer(api.stdout, process.stdout);
  prefixer(api.stderr, process.stderr);
  api.on("error", () => {
    console.error(`  [api] Python not found (${py}). Run npm install (it sets up ../server/.venv), ` +
      "or set the Python to use with ANALOGUES_PYTHON. The interface is still served.");
    api = null;
  });
  api.on("exit", (code) => {
    if (code) console.error(`  [api] stopped (code ${code}). If a module is missing: npm install.`);
    api = null;
  });
}

function arreter() {
  if (api) api.kill();
  process.exit(0);
}
process.on("SIGINT", arreter);
process.on("SIGTERM", arreter);

if (AVEC_CLIENT) {
  if (!existsSync(path.join(CLIENT, "node_modules"))) {
    console.log("  node_modules missing: run npm install (otherwise the libraries come from the Internet, unpkg).");
  }
  servirClient();
}
if (AVEC_API) lancerApi();
