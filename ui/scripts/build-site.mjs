// npm run site: prepares dist/, the online version of the interface (Cloudflare, https://astrowrap.earth).
// Copies the site as is, without node_modules: only the library files the pages load ("node_modules/..." paths
// found in the HTML and the JS) are copied, at the same paths. Online, the pages call https://api.astrowrap.earth
// (see const API in js/).
//   npx wrangler deploy        (configuration: wrangler.jsonc)

import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const DIST = join(ROOT, "dist");
const EXCLUDED = new Set(["node_modules", "dist", "scripts", "pipeline", "package.json", "package-lock.json",
                          ".gitignore", ".wrangler", "wrangler.jsonc", "README.md"]);
const MAX_BYTES = 25 * 1024 * 1024;     // size limit of a static file on Cloudflare

rmSync(DIST, { recursive: true, force: true });
mkdirSync(DIST);
for (const name of readdirSync(ROOT)) {
  if (!EXCLUDED.has(name)) cpSync(join(ROOT, name), join(DIST, name), { recursive: true });
}

// node_modules/... files cited by the pages and the scripts
const files = [];
(function walk(d) {
  for (const name of readdirSync(d)) {
    const p = join(d, name);
    if (statSync(p).isDirectory()) walk(p);
    else if (/\.(html|js|css)$/.test(name)) files.push(p);
  }
})(DIST);
const cited = new Set();
for (const f of files) {
  for (const m of readFileSync(f, "utf8").matchAll(/node_modules\/[A-Za-z0-9@._\/-]+\.(?:js|css)/g)) cited.add(m[0]);
}
let missing = 0;
for (const path of [...cited].sort()) {
  const source = join(ROOT, path);
  if (!existsSync(source)) { console.log(`  missing (CDN fallback): ${path}`); missing++; continue; }
  mkdirSync(dirname(join(DIST, path)), { recursive: true });
  cpSync(source, join(DIST, path));
  // Stylesheets: their images (Leaflet markers...) are next to them
  if (path.endsWith(".css")) {
    const images = join(dirname(source), "images");
    if (existsSync(images)) cpSync(images, join(dirname(join(DIST, path)), "images"), { recursive: true });
  }
  console.log(`  ${path}`);
}

// Checks: no file too big for Cloudflare
let total = 0, n = 0;
(function measure(d) {
  for (const name of readdirSync(d)) {
    const p = join(d, name), s = statSync(p);
    if (s.isDirectory()) { measure(p); continue; }
    n++; total += s.size;
    if (s.size > MAX_BYTES) throw new Error(`too big for Cloudflare (25 MB): ${relative(DIST, p)}`);
  }
})(DIST);
console.log(`\n  dist/: ${n} files, ${(total / 1e6).toFixed(1)} MB${missing ? ` (${missing} libraries missing: npm install)` : ""}`);
