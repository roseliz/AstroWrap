// Globe terrestre en 3D (MapLibre GL), avec bascule vers une carte 2D (projection Mercator)
// et grille des coordonnées toujours affichée.

(function () {
  const $ = (s) => document.querySelector(s);

  if (!window.maplibregl) {
    $("#globe").innerHTML = '<p class="erreur">The map library could not be loaded. Check the Internet connection, then reload the page.</p>';
    return;
  }

  const IMAGERIE = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
  const ATTRIBUTION = "Imagery © Esri, Maxar, Earthstar Geographics";
  const VUE_DEPART = { center: [-30, 22], zoom: zoomQuiCadreLaTerre(), pitch: 0, bearing: 0 };
  const AIDE_GLOBE = "Drag to rotate the globe, use the scroll wheel or two fingers to zoom, and right-drag to tilt the view. Escape returns to the whole Earth.";
  const AIDE_CARTE = "Drag to move the map, use the scroll wheel or two fingers to zoom. Escape returns to the whole Earth.";

  /** Zoom pour lequel le globe occupe environ 70 % du plus petit côté de la fenêtre.
   *  (Diamètre du globe en pixels ≈ 512 × 2^zoom / π.) */
  function zoomQuiCadreLaTerre() {
    const cote = Math.min(window.innerWidth, window.innerHeight);
    return Math.max(0, Math.log2((cote * 0.7 * Math.PI) / 512));
  }

  // ------------------------------------------------------------------ grille des coordonnées
  /** Lignes de latitude et de longitude tous les `pas` degrés, avec un point par degré
   *  pour qu'elles suivent la courbure du globe. */
  function grille(pas) {
    const traits = [];
    for (let lat = -90 + pas; lat < 90; lat += pas) {
      const c = [];
      for (let lng = -180; lng <= 180; lng += 1) c.push([lng, lat]);
      traits.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: c } });
    }
    for (let lng = -180; lng < 180; lng += pas) {
      const c = [];
      for (let lat = -90; lat <= 90; lat += 1) c.push([lng, lat]);
      traits.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: c } });
    }
    return { type: "FeatureCollection", features: traits };
  }
  // L'espacement de la grille suit le zoom : 30°, 10°, 5°, puis 1°.
  const NIVEAUX_GRILLE = [{ pas: 30, min: 0, max: 3 }, { pas: 10, min: 3, max: 5 }, { pas: 5, min: 5, max: 7 }, { pas: 1, min: 7, max: 24 }];

  const style = {
    version: 8,
    projection: { type: "globe" },
    sources: {
      satellite: { type: "raster", tiles: [IMAGERIE], tileSize: 256, maxzoom: 19, attribution: ATTRIBUTION },
      // tolerance 0 : sans elle, MapLibre simplifie les lignes en Mercator, où un parallèle est droit ; il n'en garde
      // que les bouts, et sur le globe le parallèle devient une corde droite, coupée au bord des tuiles.
      ...Object.fromEntries(NIVEAUX_GRILLE.map((n) => [`grille${n.pas}`, { type: "geojson", data: grille(n.pas), tolerance: 0 }])),
    },
    layers: [
      { id: "ocean", type: "background", paint: { "background-color": "#0E2340" } },
      { id: "satellite", type: "raster", source: "satellite" },
      // Trait blanc sur un liseré sombre, lisible sur l'océan comme sur la banquise.
      ...NIVEAUX_GRILLE.flatMap((n) => [
        { id: `grille${n.pas}-lisere`, type: "line", source: `grille${n.pas}`, minzoom: n.min, maxzoom: n.max,
          paint: { "line-color": "#000000", "line-opacity": 0.25, "line-width": 2.2 } },
        { id: `grille${n.pas}`, type: "line", source: `grille${n.pas}`, minzoom: n.min, maxzoom: n.max,
          paint: { "line-color": "#FFFFFF", "line-opacity": 0.6, "line-width": 0.8 } },
      ]),
    ],
    // Soleil en haut à gauche de l'écran : le bord éclairé du globe dessine l'atmosphère.
    light: { anchor: "viewport", position: [1.15, 210, 30] },
    sky: {
      "sky-color": "#08162E",
      "horizon-color": "#6E9BD6",
      "fog-color": "#A9C8EE",
      "sky-horizon-blend": 0.55,
      "horizon-fog-blend": 0.75,
      "fog-ground-blend": 0.9,
      "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 5, 1, 8, 0],
    },
  };

  let map;
  try {
    map = new maplibregl.Map({
      container: "globe",
      style,
      ...VUE_DEPART,
      minZoom: 0,
      maxZoom: 18,
      maxPitch: 75,
      attributionControl: { compact: true },
    });
  } catch (e) {
    // WebGL refusé par le navigateur ou le pilote graphique : carte à plat Leaflet, sans WebGL.
    console.warn("3D globe unavailable:", e.message);
    demarrerCarteSecours();
    return;
  }

  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
  map.addControl(new maplibregl.FullscreenControl(), "top-right");
  map.addControl(new maplibregl.ScaleControl({ unit: "metric", maxWidth: 120 }), "bottom-right");

  // ------------------------------------------------------------------ globe ou carte 2D
  let mode = "globe";
  function changerVue(v) {
    if (v === mode) return;
    mode = v;
    arreterRotation();
    map.setProjection({ type: mode === "globe" ? "globe" : "mercator" });
    if (mode === "carte") map.easeTo({ pitch: 0, bearing: 0, duration: 400 });
    document.querySelectorAll("[data-vue]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.vue === mode)));
    $(".aide").textContent = mode === "globe" ? AIDE_GLOBE : AIDE_CARTE;
  }
  document.querySelectorAll("[data-vue]").forEach((b) => b.addEventListener("click", () => changerVue(b.dataset.vue)));
  $(".aide").textContent = AIDE_GLOBE;

  // ------------------------------------------------------------------ coordonnées sous le curseur
  const fmt = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const lire = ({ lat, lng }) => {
    const lon = ((lng + 540) % 360) - 180;
    return `${fmt.format(Math.abs(lat))}° ${lat >= 0 ? "N" : "S"}, ${fmt.format(Math.abs(lon))}° ${lon >= 0 ? "E" : "W"}`;
  };
  const position = $("#position");
  const tactile = window.matchMedia("(hover: none)").matches;
  if (tactile) position.textContent = `View center: ${lire({ lat: VUE_DEPART.center[1], lng: VUE_DEPART.center[0] })}`;
  map.on("mousemove", (e) => { position.textContent = lire(e.lngLat); });
  map.getCanvas().addEventListener("mouseleave", () => { position.textContent = `View center: ${lire(map.getCenter())}`; });
  map.on("moveend", () => {
    if (tactile || !map.getCanvas().matches(":hover")) position.textContent = `View center: ${lire(map.getCenter())}`;
  });

  // ------------------------------------------------------------------ rotation lente au départ
  // Le globe tourne doucement jusqu'à la première interaction (sauf si l'utilisateur limite les animations).
  let enRotation = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function tourner() {
    if (!enRotation) return;
    const c = map.getCenter();
    map.easeTo({ center: [c.lng - 8, c.lat], duration: 2000, easing: (t) => t });
  }
  function arreterRotation() {
    if (!enRotation) return;
    enRotation = false;
    map.stop();
  }
  map.on("load", tourner);
  map.on("moveend", () => { if (enRotation) tourner(); });
  ["mousedown", "touchstart", "wheel", "keydown"].forEach((ev) =>
    map.getContainer().addEventListener(ev, arreterRotation, { passive: true }));

  // Échap : revenir à la Terre entière.
  window.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    arreterRotation();
    map.flyTo({ ...VUE_DEPART, zoom: zoomQuiCadreLaTerre(), duration: 1800, essential: true });
  });

  window.carteTerre = map; // pratique pour déboguer dans la console
  window.arreterRotationTerre = arreterRotation; // analogues.js arrête la rotation pour montrer les résultats

  // ------------------------------------------------------------------ secours sans WebGL
  /** Carte à plat (Leaflet, projection Web Mercator), pour les navigateurs sans WebGL. */
  function demarrerCarteSecours() {
    const avis = document.createElement("p");
    avis.className = "avis";
    avis.setAttribute("role", "status");
    avis.textContent = "The 3D view cannot be displayed: this browser could not enable WebGL (graphics card or driver refused). Here is the flat map.";
    $(".titre").appendChild(avis);
    $(".aide").textContent = AIDE_CARTE;
    document.querySelectorAll("[data-vue]").forEach((b) => {
      b.setAttribute("aria-pressed", String(b.dataset.vue === "carte"));
      if (b.dataset.vue === "globe") { b.disabled = true; b.title = "3D view unavailable in this browser"; }
    });

    const ancien = $("#globe");
    const conteneur = ancien.cloneNode(false);
    conteneur.className = "";
    ancien.replaceWith(conteneur);

    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = "node_modules/leaflet/dist/leaflet.css";                 // npm install, sinon unpkg
    css.onerror = () => { css.onerror = null; css.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"; };
    document.head.appendChild(css);
    const js = document.createElement("script");
    js.src = "node_modules/leaflet/dist/leaflet.js";
    js.onerror = () => {
      // Une balise script ne se recharge pas : on en crée une autre pour unpkg
      const secours = document.createElement("script");
      secours.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
      secours.onload = js.onload;
      secours.onerror = () => { avis.textContent = "Neither the 3D globe nor the flat map could start. Check the Internet connection."; };
      document.head.appendChild(secours);
    };
    js.onload = () => {
      const DEPART = [22, -30];
      const carte = L.map(conteneur, { worldCopyJump: true, minZoom: 2, maxZoom: 18, zoomControl: false }).setView(DEPART, 2);
      L.control.zoom({ position: "topright" }).addTo(carte);
      L.control.scale({ imperial: false, position: "bottomright" }).addTo(carte);
      L.tileLayer(IMAGERIE, { attribution: ATTRIBUTION, maxZoom: 19 }).addTo(carte);

      // Grille : même espacement que sur le globe.
      const traits = L.layerGroup().addTo(carte);
      const styles = [
        { color: "#000000", weight: 2.2, opacity: 0.25, interactive: false },
        { color: "#FFFFFF", weight: 0.8, opacity: 0.6, interactive: false },
      ];
      function majGrille() {
        traits.clearLayers();
        const z = carte.getZoom();
        const pas = z < 3 ? 30 : z < 5 ? 10 : z < 7 ? 5 : 1;
        for (const style of styles) {
          for (let lat = -90 + pas; lat < 90; lat += pas) traits.addLayer(L.polyline([[lat, -540], [lat, 540]], style));
          for (let lng = -540; lng <= 540; lng += pas) traits.addLayer(L.polyline([[-85.06, lng], [85.06, lng]], style));
        }
      }
      carte.on("zoomend", majGrille);
      majGrille();

      const f = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      const lireS = ({ lat, lng }) => {
        const lon = ((lng + 540) % 360) - 180;
        return `${f.format(Math.abs(lat))}° ${lat >= 0 ? "N" : "S"}, ${f.format(Math.abs(lon))}° ${lon >= 0 ? "E" : "W"}`;
      };
      const pos = $("#position");
      carte.on("mousemove", (e) => { pos.textContent = lireS(e.latlng); });
      carte.on("moveend", () => { pos.textContent = `View center: ${lireS(carte.getCenter())}`; });
      window.addEventListener("keydown", (e) => { if (e.key === "Escape") carte.flyTo(DEPART, 2); });
      window.carteTerre = carte;
    };
    document.head.appendChild(js);
  }
})();
