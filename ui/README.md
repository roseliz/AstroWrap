# Earth Analogues

NASA Space Apps Challenge 2026: Find locations on Earth that resemble a selected region of the Moon or Mars.

## User Journey

0. **Home screen** (`index.html` without a region): The Moon and Mars appear as rotating 3D globes, each in its own frame, rotating faster on hover. Clicking opens `lune.html` or `mars.html`. “Or explore Earth first” closes the welcome screen; “Choose a celestial body” reopens it. Clicking the site name in the navigation bar returns here from any page (`js/accueil.js`, `css/accueil.css`, reduced textures in `textures/accueil.js`).
1. On the Moon or Mars, users **paint a reference region** using H3 cells.
2. **“Compare with Earth”** saves the region on the server (`POST /api/zones`) and opens `index.html#mars/<id>` (12-character ID). `js/analogues.js` retrieves the region and starts the search (`../server`, `http://127.0.0.1:8000` by default, or `?api=…` in the URL).
3. **Loading:** The right panel shows an indicator (“Your region is being compared with the entire Earth…”) during the search (1–3 seconds), then the ranking. The search starts as soon as the page opens, alongside the criteria list. The filtering funnel is no longer replayed step by step (too slow); its stages remain in the server response and are shown in the animated recap.
4. **Results**, on the right: The top 10 sites (at least 300 km apart), each with a color-coded label (very close, close, partial, distant). Each site is evaluated over an area equal to the painted region (its footprint, outlined in white on the globe when opened); sites with more than 15% of their footprint at sea are excluded. Below, **criterion importance**: one slider per module (0 = ignored, up to 3), its percentage share, and presets (balanced, landing site, geology, etc.). The ranking is immediately recalculated in the browser (a criterion weighted 0 no longer filters). The vegetation filter and “Your region on Mars” are collapsed. On the globe, each site has a clickable numbered diamond at its exact position; opening it shows its evaluated footprint, filled and outlined in white.
5. **Site details**, on the left: Place name (Natural Earth, OpenStreetMap), one-word verdict, “Play the AstroWrap” and “Compare the terrain” buttons, then two tabs. **Data:** Side-by-side table with one row per variable (Mars/Moon region | Earth site | similarity); the panel widens. The impact of a testing campaign is in the “Responsible testing” tab of the right panel. **Overview** (default): **“Why this site?”** describes two or three similarities and the largest difference, with both values. Each criterion has a row; clicking reveals its two main values, Mars on the left and Earth on the right, on the same scale. Collapsed “Learn more about this site”: climate, terrain, soil, ice, volcanoes and caves, nearby Wikipedia, OpenStreetMap and satellite links. ‹ › or arrow keys switch sites; Escape closes the details.
6. **“Compare the terrain”** (from site details): Split screen with the Mars/Moon region on the left and Earth site on the right, in squares of equal size in kilometers, framed around the painted region. The region's **white outline** is copied unchanged around the site; the evaluated Earth footprint is dashed white.
   - **Top-down view:** Same hillshading, relative elevation coloring (lowest to highest within each square), sea in blue, scale bar.
   - **Cross-section:** Profiles of both regions on one chart (west → east or north → south), highlighting the portion inside the region; clicking a map moves the section.
   - **Slopes:** Share of terrain in each slope class, from 500 m measured deciles used by the Relief criterion (otherwise computed from the grid).
   - **3D:** Both terrain models, linked cameras, adjustable exaggeration, satellite imagery or terrain only; three.js (r147, unpkg) loads only then.

   The region outline displays the **overall terrain similarity verdict** (same thresholds and colors as the list: green = very close, yellow-green = close, yellow = partial, red = distant), in 2D and 3D, with the percentage beside the title. The score averages profile similarity (elevation range from 5th to 95th percentile and roughness, mean |Δz| between adjacent grid points along every row and column inside the region, using smaller/larger ratios) and slope similarity (shared proportion of classes).

   **A red-to-green gradient is always shown inside the region:** Each point has a terrain type, slope and roughness (elevation standard deviation over ~1.5 km), grouped into a 2D histogram. Its color equals the proportion of this terrain type in the opposite region divided by its proportion in its own region (capped at 1), smoothed. Green means that terrain also occurs on the other side; red means it is rare or absent. Identical regions are green throughout. This is **not a point-by-point comparison**: one corner of Mars need not resemble the corresponding corner of the Earth site.

   Everything fits on one screen (maps, cross-section, slopes; scrolling only on phones). Tooltips explain the cross-section, slopes, percentages, gradient scale and data credits. Terrain and imagery come from `GET /api/relief`. Escape closes the view.
7. **“✦ View the recap”** (small button in site details): Opens `bilan.html` in a new tab, an animated “Wrapped”-style recap: eleven full-screen slides, progress bar, little text, split “Mars | Earth” where suitable. In order: score; funnel (from 613,252 regions to one site); criteria radar; side-by-side 3D terrain (only when terrain is similar); day/night temperatures; rock composition; similarities; differences; best-matching use profile (weight presets); site limitations (vegetation, missing/partial data, gravity and pressure that no Earth site reproduces); summary. Everything comes from the server; slides with missing data are skipped. ‹ › or arrows navigate, P pauses, Escape closes. URL carries region ID, weights and score: `bilan.html?w=…&s=…&n=…#mars/<zone>/<cellule>`.
8. **Known analogues** (below the site list): Sites scientists already compare with Mars or the Moon (Devon Island, Atacama, Dry Valleys, etc.), each at its **actual rank** for the painted region (“Top 1%”, 263rd of 20,326 candidates), showing whether it passes the funnel or where it is excluded. They are never added artificially to the ranking; diamonds mark them on the globe and open their details. Mineral analogues (Rio Tinto, Lake Salda) are marked out of scope. Global validation of these pairs remains in the API (`GET /api/validation`; see `../server/README.md`).

The server must be running (see `../server/README.md`); otherwise the page indicates this.

## Pages

A **navigation bar** (`js/navigation.js`, `css/navigation.css`) appears on every page except the recap. The site name returns home; **Moon** and **Mars** open region painting; **Earth** reopens the latest comparison (saved in the browser and indicated by a colored dot), otherwise the explorable globe (`index.html#terre`, without welcome screen); **About** is on the right. On phones, ☰ expands links. The `?api=…` parameter follows navigation.

- `index.html`: Home (Moon/Mars selection), then 3D Earth (MapLibre GL), switchable to 2D, and comparison results.
- `bilan.html`: A site's AstroWrap, animated card-by-card recap (`js/bilan.js`, `css/bilan.css`), opened from “Play the AstroWrap” or the “Your AstroWrap is ready” screen after the first search. Logo and favicon in `images/` (transparent background).
- `apropos.html`: What the tool does, methodology, limitations, data sources and credits, team.
- `lune.html`: 3D Moon (globe.gl), 2D switch and region selection. Displays poles, unlike MapLibre beyond 85° latitude.
- `mars.html`: 3D Mars (globe.gl), same functions as the Moon, with a halo for its thin atmosphere.

The coordinate grid is always visible. Moon and Mars 2D maps use an **equirectangular projection**, with straight latitude/longitude axes as on NASA maps. Switching between globe and map preserves the region in view.

## Running

From `ui/`, with Node.js 18 or later and Python 3.9 to 3.12:

```bash
npm install
npm start
```

`npm install` fetches the JavaScript libraries (`node_modules/`), then creates `server/.venv` with the first Python found (`ANALOGUES_PYTHON`, `py -3` on Windows, `python3`, `python`) and installs `server/requirements.txt`. A failure there is reported but does not stop the install. Rerun it after a `git pull`. `ANALOGUES_SANS_PYTHON=1` skips the Python step.

`npm start` serves the interface at http://localhost:8080 and starts the server from the repository root with `server/.venv`: `python -m uvicorn server.main:app --host 127.0.0.1 --port 8000`.

| Command | Effect |
|---|---|
| `npm start` | Interface + server (the server is not started again if one already answers on the API port) |
| `npm run client` | Interface only (server elsewhere: `?api=http://host:port` in the URL) |
| `npm run api` | Server only |

Ports: `PORT` (interface, default 8080) and `API_PORT` (server, default 8000). With another API port, open the URL that `npm start` prints: it carries `?api=…`. The server reads the module results from `pretreatment_data/` at the repository root (or `ANALOGUES_DATA`; see `../server/README.md`).

Libraries (MapLibre GL, globe.gl, Leaflet, h3-js, three.js) load from `node_modules/`; if missing (page opened without `npm install`), pages load them from unpkg or jsDelivr. Internet is still required for imagery (NASA Trek, Esri) and fonts.

| Action | Mouse | Keyboard | Touch |
|---|---|---|---|
| Rotate globe | Drag | Arrow keys | Drag |
| Zoom | Wheel, double-click | + and − | Pinch |
| Reset full view | | Escape | |

## Landmarks (Moon and Mars)

Known sites are marked on globe and 2D map: solid circles for landing sites (Apollo, Viking, Curiosity, Perseverance, etc.); rings for terrain features (Olympus Mons, Hellas, Tycho, Shackleton, etc.). Secondary names appear when zoomed in. Hovering displays descriptions; clicking moves the view. List and coordinates: `js/reperes.js`.

## Reference Region Selection (Moon and Mars)

The **“Reference Region”** panel on the right lets users paint the region to compare with Earth, on both the globe and 2D map.

| Action | Mouse | Keyboard |
|---|---|---|
| Paint cells | “Paint” tool, then drag | B |
| Erase | “Erase” tool, or Shift while painting | E |
| Return to navigation | “Navigate” tool | V |
| Pan without leaving brush | | Hold Space + drag |
| Brush size | Small, Medium, Large | [ and ] |
| Undo | “Undo” button | Ctrl+Z |

- **Cells are H3 resolution 6** (Mars: ~10 km²; Moon: ~2.7 km²), exactly the cells preprocessing will use.
- **Brush follows zoom.** From afar it places large cells subsequently subdivided into resolution 6; up close, individual cells.
- **Panel displays** area, number of cells, number of disconnected parts and center. Regions must contain 10–60,000 cells.
- **URLs never contain H3 cells.** On Mars/Moon the region is stored in browser `localStorage` and restored on reload. For Earth it passes through the server (short ID, `server/cache/zones/`), also working in browsers that isolate locally opened `file://` files (Firefox). `index.html#mars/<id>` is shareable while the server retains its cache. When the server is down, browser storage is used. Legacy `#zone=...` addresses are still read and cleaned up.
- **“Export” downloads JSON** (compacted cells, resolution, area, center). In Python, `h3.uncompact_cells(compacted_cells, 6)` yields the complete list.

## Project Structure

```text
package.json                         npm install, npm start (libraries, scripts)
scripts/demarrer.mjs                 npm start: serves the interface and starts the server
scripts/installer-api.mjs            After npm install: server/.venv and server/requirements.txt
index.html                           Home and Earth globe
css/style.css
js/accueil.js                        Home: 3D Moon and Mars (three.js), click to open page
css/accueil.css
js/globe-terre.js                    MapLibre globe, 2D map, grid, coordinates
js/analogues.js                      Mars/Moon comparison (server, layers, panel, known analogues)
css/analogues.css
apropos.html                         About: methodology, limitations, sources (css/pages.css)
js/navigation.js                     Navigation on every page (except recap)
css/navigation.css
lune.html                            Moon globe
css/lune.css
js/globe-lune.js                     globe.gl: textures, terrain, controls, coordinates
mars.html                            Mars globe
css/mars.css
js/globe-mars.js                     globe.gl: textures, NASA Mars Trek tiles, terrain, controls
js/carte-plane.js                    Shared 2D Leaflet map for lune.html and mars.html
js/selection-zone.js                 H3 reference region painting (Moon and Mars)
css/selection.css                    “Reference Region” panel
js/reperes.js                        Known landing sites and terrain landmarks
css/reperes.css
textures/                            Moon/Mars imagery encoded in .js
```

`js/cle-carto.js` and `js/cle-carto.exemple.js` are no longer used: the “Map” basemap was removed from the Earth page. They can be deleted.

## Moon Textures

Images come from the NASA Scientific Visualization Studio [CGI Moon Kit](https://svs.gsfc.nasa.gov/4720): LROC color mosaic and LOLA terrain. They are encoded in `.js` files because browsers refuse to use a local image as a 3D texture when the page is opened by double-clicking. The page loads 4096 px first, then 8192 px if the graphics card supports it.

For greater detail (e.g., 16K), download the images from NASA and run:

```bash
pip install pillow
python scripts/construire_textures_lune.py --couleur lroc_color_poles_16k.tif --relief ldem_3_8bit.jpg
```

NASA notes that this mosaic is intended for display, not scientific analysis: measurements will come from the source data (LROC WAC, LOLA).

## Mars Imagery

The page immediately displays an embedded 1440 px NASA map (official NASA-3D-Resources repository), which works offline. The browser then assembles a 4096 px version from NASA Mars Trek tiles: Viking MDIM 2.1 color mosaic and MOLA terrain. If NASA's server rejects the tiles, the page reports this and retains the embedded map.

In 2D, Trek tiles display as ordinary images without requesting server authorization, allowing full resolution (Viking down to ~232 m/px). Similarly, the Moon's 2D map attempts to overlay Moon Trek tiles (LRO WAC mosaic, ~100 m/px) on the embedded image.
