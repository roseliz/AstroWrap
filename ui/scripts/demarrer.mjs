// npm start: serves the interface (http://localhost:8080) and starts the application server (FastAPI, port 8000).
//
//   npm start          Interface + server
//   npm run client     Interface only (the server runs elsewhere: add ?api=http://host:port to the URL)
//   npm run api        Server only
//
// The server runs from the repository root as `python -m uvicorn server.main:app`, with the Python of
// ANALOGUES_PYTHON, else server/.venv (created by npm install), else the system Python.
// If a server already answers on API_PORT, it is not started a second time.
//
// Environment variables: PORT (interface, default 8080), API_PORT (server, default 8000).

import { spawn } from "node:child_process";
import { existsSync, createReadStream, statSync } from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const UI = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = path.resolve(UI, "..");
const SERVER = path.join(ROOT, "server");
const PORT = Number(process.env.PORT || 8080);
const API_PORT = Number(process.env.API_PORT || 8000);
const API_URL = `http://127.0.0.1:${API_PORT}`;
const args = new Set(process.argv.slice(2));
const WITH_UI = !args.has("--api-seule");
const WITH_API = !args.has("--sans-api");

const TYPES = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".map": "application/json",
  ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
  ".ico": "image/x-icon", ".woff": "font/woff", ".woff2": "font/woff2", ".wasm": "application/wasm", ".md": "text/plain; charset=utf-8",
};

// ------------------------------------------------------------------ Interface (static files)
function serveUi() {
  const server = http.createServer((req, res) => {
    let urlPath;
    try {
      urlPath = decodeURIComponent(new URL(req.url, "http://x").pathname);
    } catch {
      res.writeHead(400).end();
      return;
    }
    let file = path.normalize(path.join(UI, urlPath));
    if (file !== UI && !file.startsWith(UI + path.sep)) { res.writeHead(403).end(); return; }   // no ../
    if (existsSync(file) && statSync(file).isDirectory()) file = path.join(file, "index.html");
    if (!existsSync(file)) {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" }).end(`Not found: ${urlPath}`);
      return;
    }
    res.writeHead(200, {
      "Content-Type": TYPES[path.extname(file).toLowerCase()] || "application/octet-stream",
      "Cache-Control": "no-cache",                     // development: always the latest version
    });
    createReadStream(file).pipe(res);
  });
  server.on("error", (e) => {
    console.error(e.code === "EADDRINUSE"
      ? `Port ${PORT} is already in use. Pick another one: PORT=8081 npm start (PowerShell: $env:PORT=8081; npm start)`
      : e.message);
    process.exit(1);
  });
  server.listen(PORT, () => {
    // The pages call http://127.0.0.1:8000 by default; any other API port goes in the URL.
    const query = API_PORT === 8000 ? "" : `?api=${encodeURIComponent(API_URL)}`;
    console.log(`\n  Terrestrial Analogs: http://localhost:${PORT}/${query}\n`);
  });
}

// ------------------------------------------------------------------ Application server (FastAPI)
function python() {
  const candidates = [
    process.env.ANALOGUES_PYTHON,
    path.join(SERVER, ".venv", "Scripts", "python.exe"),   // Windows
    path.join(SERVER, ".venv", "bin", "python"),            // Linux, macOS
  ].filter(Boolean);
  return candidates.find((p) => existsSync(p)) || (process.platform === "win32" ? "python" : "python3");
}

// Data folder this repository's server reads (same rule as server/core/config.py).
const DATA_DIR = path.resolve(process.env.ANALOGUES_DATA || path.join(ROOT, "pretreatment_data"));

/** Data folder of the server already answering on API_PORT, or null when nothing answers. */
async function runningApiData() {
  try {
    const r = await fetch(`${API_URL}/api/health`, { signal: AbortSignal.timeout(1500) });
    if (!r.ok) return "";
    const health = await r.json();
    return typeof health.data === "string" ? health.data : "";
  } catch {
    return null;
  }
}

let api = null;
async function startApi() {
  const running = await runningApiData();
  if (running !== null) {
    if (running && path.resolve(running).toLowerCase() === DATA_DIR.toLowerCase()) {
      console.log(`  [api] already running on ${API_URL}`);
      return;
    }
    // Another server (another checkout, an old version...) holds the port: do not use it silently.
    console.error(`  [api] port ${API_PORT} is taken by another server (data: ${running || "unknown"}), ` +
      `not this repository's (data: ${DATA_DIR}).\n` +
      `  [api] Stop it, or use another port: API_PORT=8001 npm start (PowerShell: $env:API_PORT=8001; npm start)`);
    if (!WITH_UI) process.exit(1);
    return;
  }
  const py = python();
  const command = ["-m", "uvicorn", "server.main:app", "--host", "127.0.0.1", "--port", String(API_PORT)];
  console.log(`  [api] ${py} ${command.join(" ")}  (in ${ROOT})`);
  api = spawn(py, command, { cwd: ROOT, env: process.env });
  const prefix = (stream, output) => {
    let rest = "";
    stream.on("data", (chunk) => {
      const lines = (rest + chunk).split(/\r?\n/);
      rest = lines.pop();
      lines.forEach((l) => output.write(`  [api] ${l}\n`));
    });
  };
  prefix(api.stdout, process.stdout);
  prefix(api.stderr, process.stderr);
  api.on("error", () => {
    console.error(`  [api] Python not found (${py}). Run npm install (it sets up server/.venv), ` +
      "or point ANALOGUES_PYTHON to a Python. The interface is still served.");
    api = null;
  });
  api.on("exit", (code) => {
    if (code) console.error(`  [api] stopped (code ${code}). If a module is missing: npm install.`);
    api = null;
    if (!WITH_UI) process.exit(code || 0);
  });
}

function stop() {
  if (api) api.kill();
  process.exit(0);
}
process.on("SIGINT", stop);
process.on("SIGTERM", stop);

if (WITH_UI) {
  if (!existsSync(path.join(UI, "node_modules"))) {
    console.log("  node_modules missing: run npm install (until then the libraries come from unpkg or jsDelivr).");
  }
  serveUi();
}
if (WITH_API) startApi();
