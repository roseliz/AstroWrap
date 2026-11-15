// 3D Martian globe (globe.gl / three.js).
// Immediate display with the built-in NASA texture (1440 px), then replacement with a detailed
// version assembled from NASA Mars Trek tiles, if the browser can load them.

(function () {
  const $ = (s) => document.querySelector(s);
  const RAYON_KM = 3389.5;
  const VUE_ENTIERE = { lat: 10, lng: 60, altitude: 2.4 };   // altitude in Martian radii (recalculated further down)
  const ALTITUDE_MIN = 0.03;   // ~100 km
  const ALTITUDE_MAX = 6;

  // NASA Mars Trek tiles (geographic grid: level n = 2^(n+1) columns x 2^n rows of 256 px)
  const TREK = "https://trek.nasa.gov/tiles/Mars/EQ";
  const PRODUITS = {
    viking: { id: "Mars_Viking_MDIM21_ClrMosaic_global_232m", ext: "jpg", niveau: 3, nom: "Viking mosaic" },
    relief: { id: "mola128_mola64_merge_90Nto90S_SimpleC_clon0", ext: "png", niveau: 2, nom: "MOLA elevation" },
  };

  const urlTuiles = (cle) => {
    const p = PRODUITS[cle];
    return `${TREK}/${p.id}/1.0.0//default/default028mm/{z}/{y}/{x}.${p.ext}`;
  };
  // In 2D, tiles are displayed as simple images: no CORS authorization needed,
  // so full Trek resolution is available (Viking up to level 7, ~232 m/px).
  const tuiles2D = (cle) => ({ url: urlTuiles(cle), maxZoom: cle === "viking" ? 7 : 6 });

  if (!window.TEXTURE_MARS) {
    $("#chargement").textContent = "The Mars texture cannot be found (textures/mars-surface.js).";
    return;
  }

  const conteneur = $("#globe");
  // null if 3D is impossible in this browser: the page then switches to the 2D map.
  const globe = window.creerGlobe3D ? window.creerGlobe3D(conteneur) : null;
  if (globe) globe
    .width(window.innerWidth)
    .height(window.innerHeight)
    .backgroundColor("rgba(0,0,0,0)")
    .globeImageUrl(window.TEXTURE_MARS)
    .showAtmosphere(true)
    .atmosphereColor("#E9B58F")
    .atmosphereAltitude(0.04)
    .showGraticules(true)
    .globeCurvatureResolution(2);

  /** Altitude for which Mars occupies about 72% of the window's smallest side. */
  function altitudeQuiCadreMars() {
    const fov = globe ? globe.camera().fov : 50;
    const demiV = (fov / 2) * (Math.PI / 180);
    const demiH = Math.atan(Math.tan(demiV) * (window.innerWidth / window.innerHeight));
    const angle = 0.72 * Math.min(demiV, demiH);
    return Math.min(6, 1 / Math.sin(angle) - 1);
  }
  VUE_ENTIERE.altitude = altitudeQuiCadreMars();
  if (globe) globe.pointOfView(VUE_ENTIERE, 0);

  // ------------------------------------------------------------------ lighting
  const lumieres = globe ? globe.lights() : [];
  const soleil = lumieres.find((l) => l.isDirectionalLight);
  const ambiante = lumieres.find((l) => l.isAmbientLight);
  if (ambiante) ambiante.intensity = 0.5 * Math.PI;
  if (soleil) {
    soleil.intensity = 0.9 * Math.PI;
    soleil.position.set(-1, 0.8, 1);
    const camera = globe.camera();
    camera.add(soleil);
    if (!camera.parent) globe.scene().add(camera);
  }

  const materiau = globe ? globe.globeMaterial() : null;
  const anisotropie = globe ? globe.renderer().capabilities.getMaxAnisotropy() : 1;

  /** Applies an image to the globe, then adjusts its filtering once the texture is created. */
  function poserImage(url) {
    if (!globe) return;
    const avant = materiau.map;
    globe.globeImageUrl(url);
    const attente = setInterval(() => {
      const t = materiau.map;
      if (t && t !== avant) {
        clearInterval(attente);
        t.anisotropy = anisotropie;
        t.needsUpdate = true;
      }
    }, 150);
    setTimeout(() => clearInterval(attente), 15000);
  }

  // ------------------------------------------------------------------ detailed images (NASA Mars Trek)
  const images = { viking: null, relief: null };
  let detailIndisponible = false;
  const enCours = {};
  const etat = $("#etat-images");

  /** Assembles tiles of a Trek product into a single equirectangular image (data URL), or null. */
  function assembler(cle) {
    if (enCours[cle]) return enCours[cle];
    const p = PRODUITS[cle];
    const T = 256, colonnes = 2 ** (p.niveau + 1), lignes = 2 ** p.niveau;
    const canvas = document.createElement("canvas");
    canvas.width = colonnes * T;
    canvas.height = lignes * T;
    const ctx = canvas.getContext("2d");
    const taches = [];
    for (let y = 0; y < lignes; y++) for (let x = 0; x < colonnes; x++) taches.push([x, y]);
    let echecs = 0;

    const charger = ([x, y]) => new Promise((ok) => {
      const img = new Image();
      img.crossOrigin = "anonymous";
      const minuterie = setTimeout(() => { echecs++; ok(); }, 20000);
      img.onload = () => { clearTimeout(minuterie); ctx.drawImage(img, x * T, y * T, T, T); ok(); };
      img.onerror = () => { clearTimeout(minuterie); echecs++; ok(); };
      img.src = urlTuiles(cle).replace("{z}", p.niveau).replace("{y}", y).replace("{x}", x);
    });

    enCours[cle] = (async () => {
      const file = taches.slice();
      const travailleurs = Array.from({ length: 8 }, async () => {
        while (file.length) {
          await charger(file.shift());
          if (echecs > 3 && echecs > taches.length * 0.1) return; // server refuses: no need to insist
        }
      });
      await Promise.all(travailleurs);
      if (echecs > taches.length * 0.1) return null;
      try {
        return canvas.toDataURL(p.ext === "png" ? "image/png" : "image/jpeg", 0.9);
      } catch (e) {
        return null; // "tainted" image: server does not allow its usage in WebGL
      }
    })();
    return enCours[cle];
  }

  async function chargerImagesDetaillees() {
    etat.textContent = "Loading the detailed version (NASA Mars Trek)…";
    const [viking, relief] = await Promise.all([assembler("viking"), assembler("relief")]);
    images.viking = viking;
    images.relief = relief;
    if (viking) {
      poserImage(viking);
      etat.textContent = "";
    } else {
      detailIndisponible = true;
      if (mode === "globe") etat.textContent = "Detailed version unavailable: showing low resolution.";
    }
    if (viking && plane) plane.changerImage(viking);
    if (relief && globe) {
      globe.bumpImageUrl(relief);
      appliquerRelief();
    }
  }

  // ------------------------------------------------------------------ relief (always active in 3D)
  function appliquerRelief() {
    if (!materiau) return;
    materiau.bumpScale = 8;
    materiau.needsUpdate = true;
  }

  // ------------------------------------------------------------------ camera controls
  const controles = globe ? globe.controls() : {};
  controles.enableDamping = true;
  controles.dampingFactor = 0.08;
  controles.rotateSpeed = 0.6;
  controles.zoomSpeed = 0.8;
  const rayonScene = globe ? globe.getGlobeRadius() : 100;
  controles.minDistance = rayonScene * (1 + ALTITUDE_MIN);
  controles.maxDistance = rayonScene * (1 + ALTITUDE_MAX);

  function ajusterVitesse() {
    if (!globe) return;
    const alt = globe.pointOfView().altitude;
    controles.rotateSpeed = Math.min(0.6, 0.12 + alt * 0.25);
  }

  const animationsReduites = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  controles.autoRotate = !animationsReduites;
  controles.autoRotateSpeed = 0.35;
  function arreterRotation() { controles.autoRotate = false; }
  ["pointerdown", "wheel", "touchstart", "keydown"].forEach((ev) =>
    conteneur.addEventListener(ev, arreterRotation, { passive: true }));

  function deplacer(vue, duree) {
    const d = animationsReduites ? 0 : duree;
    globe.pointOfView(vue, d);
    setTimeout(majAltitude, d + 40);
  }
  function allerA(vue, duree = 1600) {
    arreterRotation();
    if (mode === "carte") {
      if (vue === VUE_ENTIERE) plane.cadrerMonde(!animationsReduites);
      else plane.allerA(vue.lat, vue.lng, altitudeVersLargeur(vue.altitude), !animationsReduites);
      return;
    }
    deplacer(vue, duree);
  }
  function zoomer(facteur) {
    arreterRotation();
    if (mode === "carte") { plane.zoomer(facteur < 1 ? 0.75 : -0.75); return; }
    const pov = globe.pointOfView();
    const alt = Math.min(ALTITUDE_MAX, Math.max(ALTITUDE_MIN, pov.altitude * facteur));
    deplacer({ ...pov, altitude: alt }, 400);
  }


  // ------------------------------------------------------------------ 2D map (equirectangular projection)
  let mode = "globe";
  let plane = null;
  const aide = $(".aide");
  const AIDE_GLOBE = aide.textContent;
  const AIDE_CARTE = "Drag to move the map, use the scroll wheel or two fingers to zoom, Escape to see everything. Near the poles, a flat map stretches the terrain: its true shape shows on the globe.";
  /** 3D camera horizontal half-field-of-view angle. */
  const demiH = () => Math.atan(Math.tan(((globe ? globe.camera().fov : 50) / 2) * (Math.PI / 180)) * (window.innerWidth / window.innerHeight));
  /** Approximate correspondence between 3D altitude and visible 2D terrain width (degrees). */
  const altitudeVersLargeur = (a) => Math.min(360, (2 * a * Math.tan(demiH()) * 180) / Math.PI);
  const largeurVersAltitude = (w) => Math.min(ALTITUDE_MAX, Math.max(ALTITUDE_MIN, ((w * Math.PI) / 180) / (2 * Math.tan(demiH()))));

  function creerCarte() {
    plane = new CartePlane({
      element: $("#carte2d"),
      rayonKm: RAYON_KM,
      image: images.viking || window.TEXTURE_MARS,
      tuiles: tuiles2D("viking"),
      surMouvement: majAltitude,
      surSurvol: (c) => {
        survol = Boolean(c);
        position.textContent = c ? lire(c) : `View center: ${lire(plane.centre())}`;
      },
    });
    plane.afficherGrille(true);
  }

  /** Switches from the globe to the 2D map (or vice versa) while keeping roughly the same area on screen. */
  function changerVue(v) {
    if (v === mode || !globe) return;
    if (v === "carte" && !window.L) {
      position.textContent = "The 2D map could not be loaded (Internet connection required).";
      return;
    }
    arreterRotation();
    if (v === "carte") {
      const pov = globe.pointOfView();
      $("#globe").hidden = true;
      $("#carte2d").hidden = false;
      if (!plane) creerCarte(); else plane.rafraichir();
      if (pov.altitude >= VUE_ENTIERE.altitude * 0.9) plane.cadrerMonde(false);
      else plane.allerA(pov.lat, pov.lng, altitudeVersLargeur(pov.altitude), false);
      globe.pauseAnimation();
    } else {
      const c = plane.centre();
      const w = plane.largeurDeg();
      $("#carte2d").hidden = true;
      $("#globe").hidden = false;
      globe.resumeAnimation();
      globe.pointOfView({ lat: c.lat, lng: c.lng, altitude: w >= 300 ? VUE_ENTIERE.altitude : largeurVersAltitude(w) }, 0);
    }
    mode = v;
    document.querySelectorAll("[data-vue]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.vue === mode)));
    survol = false;
    aide.textContent = mode === "carte" ? AIDE_CARTE : AIDE_GLOBE;
    // In 2D, Trek tiles are displayed directly: the detailed version message only concerns 3D.
    etat.textContent = mode === "globe" && detailIndisponible ? "Detailed version unavailable: showing low resolution." : "";
    majAltitude();
    (mode === "carte" ? $("#carte2d") : $("#globe")).focus({ preventScroll: true });
    document.dispatchEvent(new Event("vue:changee"));
  }
  document.querySelectorAll("[data-vue]").forEach((b) => b.addEventListener("click", () => changerVue(b.dataset.vue)));

  $("#zoom-plus").addEventListener("click", () => zoomer(0.6));
  $("#zoom-moins").addEventListener("click", () => zoomer(1.6));
  $("#plein-ecran").addEventListener("click", () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen?.();
  });

  // Keyboard: arrows to rotate, + and − to zoom, Escape to see the whole planet again.
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { allerA(VUE_ENTIERE); return; }
    if (e.target.closest && e.target.closest("input")) return;
    if (mode === "carte") {
      const d = { ArrowLeft: [-120, 0], ArrowRight: [120, 0], ArrowUp: [0, -120], ArrowDown: [0, 120] }[e.key];
      if (d) { e.preventDefault(); plane.deplacer(d[0], d[1]); }
      else if (e.key === "+" || e.key === "=") zoomer(0.7);
      else if (e.key === "-" || e.key === "_") zoomer(1.4);
      return;
    }
    const pov = globe.pointOfView();
    const pas = Math.max(1, 12 * Math.min(1, pov.altitude));
    const mouvements = {
      ArrowLeft: { lng: pov.lng - pas }, ArrowRight: { lng: pov.lng + pas },
      ArrowUp: { lat: Math.min(89.9, pov.lat + pas) }, ArrowDown: { lat: Math.max(-89.9, pov.lat - pas) },
    };
    if (mouvements[e.key]) {
      e.preventDefault();
      arreterRotation();
      deplacer({ ...pov, ...mouvements[e.key] }, 250);
    } else if (e.key === "+" || e.key === "=") zoomer(0.7);
    else if (e.key === "-" || e.key === "_") zoomer(1.4);
  });

  // ------------------------------------------------------------------ coordinates and altitude
  const fmt = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtKm = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  const lire = ({ lat, lng }) => {
    const lon = ((lng + 540) % 360) - 180;
    return `${fmt.format(Math.abs(lat))}° ${lat >= 0 ? "N" : "S"}, ${fmt.format(Math.abs(lon))}° ${lon >= 0 ? "E" : "W"}`;
  };
  const position = $("#position");
  const tactile = window.matchMedia("(hover: none)").matches;

  let survol = false;
  function majAltitude() {
    if (mode === "carte" && plane) {
      $("#altitude").textContent = `View width: ${fmtKm.format(plane.largeurKm())} km`;
      if (tactile || !survol) position.textContent = `View center: ${lire(plane.centre())}`;
      return;
    }
    if (!globe) return;
    const pov = globe.pointOfView();
    $("#altitude").textContent = `View altitude: ${fmtKm.format(pov.altitude * RAYON_KM)} km`;
    if (tactile || !survol) position.textContent = `View center: ${lire(pov)}`;
    ajusterVitesse();
  }
  if (globe) globe.onZoom(majAltitude);

  /** Martian coordinates under a point on the screen: intersection of the camera ray with the sphere. */
  function coordsSousPoint(x, y) {
    if (!globe) return null;
    const cam = globe.camera();
    cam.updateMatrixWorld();
    const nx = (x / conteneur.clientWidth) * 2 - 1;
    const ny = 1 - (y / conteneur.clientHeight) * 2;
    const mul = (m, v) => [0, 1, 2, 3].map((r) => m[r] * v[0] + m[4 + r] * v[1] + m[8 + r] * v[2] + m[12 + r] * v[3]);
    let p = mul(cam.projectionMatrixInverse.elements, [nx, ny, 0.5, 1]);
    p = mul(cam.matrixWorld.elements, p.map((c) => c / p[3]));
    const o = [cam.matrixWorld.elements[12], cam.matrixWorld.elements[13], cam.matrixWorld.elements[14]];
    let d = [p[0] - o[0], p[1] - o[1], p[2] - o[2]];
    const n = Math.hypot(...d);
    d = d.map((c) => c / n);
    const R = globe.getGlobeRadius();
    const b = o[0] * d[0] + o[1] * d[1] + o[2] * d[2];
    const disc = b * b - (o[0] ** 2 + o[1] ** 2 + o[2] ** 2 - R * R);
    if (disc < 0) return null;
    const t = -b - Math.sqrt(disc);
    if (t < 0) return null;
    return globe.toGeoCoords({ x: o[0] + t * d[0], y: o[1] + t * d[1], z: o[2] + t * d[2] });
  }

  conteneur.addEventListener("mousemove", (e) => {
    if (!globe) return;
    const r = conteneur.getBoundingClientRect();
    const c = coordsSousPoint(e.clientX - r.left, e.clientY - r.top);
    survol = Boolean(c);
    position.textContent = c ? lire(c) : `View center: ${lire(globe.pointOfView())}`;
  });
  conteneur.addEventListener("mouseleave", () => {
    if (!globe) return;
    survol = false;
    position.textContent = `View center: ${lire(globe.pointOfView())}`;
  });

  // ------------------------------------------------------------------ startup
  if (globe) globe.onGlobeReady(() => {
    $("#chargement").hidden = true;
    window.renforcerGrille3D(globe);
    const t = materiau.map;
    if (t) { t.anisotropy = anisotropie; t.needsUpdate = true; }
    majAltitude();
    chargerImagesDetaillees();
  });
  else demarrerSans3D();

  /** Without WebGL (or without globe.gl), the page opens directly on the 2D map, which does not need it. */
  function demarrerSans3D() {
    $("#chargement").hidden = true;
    $("#globe").hidden = true;
    const avis = $("#avis-3d");
    avis.hidden = false;
    if (!window.L) {
      avis.textContent = "Neither the 3D view nor the 2D map could start. Check the Internet connection, then try another browser.";
      return;
    }
    mode = "carte";
    $("#carte2d").hidden = false;
    creerCarte();
    plane.cadrerMonde(false);
    document.querySelectorAll("[data-vue]").forEach((b) => {
      b.setAttribute("aria-pressed", String(b.dataset.vue === "carte"));
      if (b.dataset.vue === "globe") { b.disabled = true; b.title = "3D view unavailable in this browser"; }
    });
    aide.textContent = "Drag to move the map, use the scroll wheel or two fingers to zoom. Near the poles, a flat map stretches the terrain.";
    majAltitude();
  }

  window.addEventListener("resize", () => {
    if (globe) globe.width(window.innerWidth).height(window.innerHeight);
    VUE_ENTIERE.altitude = altitudeQuiCadreMars();
    if (plane) plane.rafraichir();
  });

  // ------------------------------------------------------------------ interface for area selection
  // Used by js/selection-zone.js (H3 tiles), loaded after this file.
  window.vueCorps = {
    corps: "mars",
    rayonKm: RAYON_KM,
    globe,
    conteneur,
    mode: () => mode,
    plane: () => plane,
    coordsSousPoint,
    /** Visible terrain width in km: used to set brush size. */
    largeurVueKm() {
      if (mode === "carte" && plane) return plane.largeurKm();
      if (!globe) return 2 * RAYON_KM;
      return Math.min(2 * RAYON_KM, 2 * globe.pointOfView().altitude * Math.tan(demiH()) * RAYON_KM);
    },
    arreterRotation,
    /** Flies to a point; altitude in body radii (converted to view width in 2D). */
    allerA: (lat, lng, altitude) => allerA({ lat, lng, altitude }),
  };

  window.globeMars = globe; // handy for debugging in the console
})();