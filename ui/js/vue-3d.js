// Comparer les reliefs : la zone peinte sur Mars (ou la Lune) et un site retenu sur la Terre, côte à côte, à la même
// échelle (même carré en km, cadré sur la zone peinte). Le contour blanc de la zone est reporté tel quel (même forme,
// même surface) autour du site ; en pointillé blanc, l'empreinte jugée sur Terre (disque de même surface,
// services/empreinte.py).
//
// Ce qui se lit le mieux est en premier :
// - deux cartes vues de dessus, même ombrage, couleur d'altitude relative (du plus bas au plus haut de chaque carré),
//   la mer en bleu ;
// - une coupe à travers les deux zones, sur le même graphique (cliquer sur une carte la déplace) ;
// - la répartition des pentes : les déciles mesurés à 500 m que compare le critère Relief (POST /api/search/detail),
//   ou, à défaut, les pentes de la grille ;
// - en option, les deux maquettes en 3D (three.js r147, chargé à la demande), caméras liées ;
// - la zone est colorée selon la ressemblance du relief (vert : très proche ... rouge : éloigné), la même des deux
//   côtés : moyenne de la ressemblance des coupes (dénivelé et rugosité sur toute la zone, toutes les lignes et
//   colonnes de la grille ; elle ne dépend donc pas de la coupe affichée) et de celle des pentes (part commune des
//   classes). Pas de comparaison point par point : rien n'oblige le coin nord-est de la
//   zone de Mars à ressembler au coin nord-est du site ;
// - à l'intérieur de la zone, un dégradé du rouge au vert : à chaque endroit, le terrain local (pente et rugosité sur
//   ~1,5 km) se retrouve-t-il ailleurs dans la zone d'en face ? Vert : oui, c'est un terrain courant de l'autre côté ;
//   rouge : il n'y existe pas (bord de cratère sur Mars, vallée encaissée sur Terre...).
//
// Le serveur fournit pour chaque côté une grille d'altitude de 256 x 256 points sur le même carré et l'image drapée
// (GET /api/relief : MOLA, LOLA, Copernicus ; Trek, Esri).
//
// Utilisation (js/analogues.js) :
//   window.vue3D.ouvrir({ api, corps, zone, site: { lat, lon, h3, nom, empreinte }, pentes: { zone, site } | null })

(function () {
  // node_modules (npm install), sinon unpkg
  const THREE_URL = ["node_modules/three/build/three.min.js", "https://unpkg.com/three@0.147.0/build/three.min.js"];
  const ORBIT_URL = ["node_modules/three/examples/js/controls/OrbitControls.js",
    "https://unpkg.com/three@0.147.0/examples/js/controls/OrbitControls.js"];
  const RAYON_KM = { earth: 6371.0088, mars: 3389.5, moon: 1737.4 };
  const NOMS = { mars: "Mars", moon: "Moon", earth: "Earth" };
  const COULEURS = { mars: "#E0794F", moon: "#C9CED6", earth: "#4FD1FF" };
  const EMPREINTE = "rgba(255,255,255,0.85)";      // pointillé : ne se confond avec aucune couleur de niveau
  // Mêmes seuils et couleurs que la liste des sites (js/analogues.js)
  const NIVEAUX = [
    { min: 0.8, nom: "Very close", couleur: "#3DDC97" },
    { min: 0.6, nom: "Close", couleur: "#B9E05A" },
    { min: 0.4, nom: "Partial", couleur: "#F2C14E" },
    { min: -1, nom: "Far", couleur: "#F2545B" },
  ];
  const NEUTRE = { nom: "", couleur: "#FFFFFF" };
  const niveau = (s) => (s == null || Number.isNaN(s) ? NEUTRE : NIVEAUX.find((n) => s >= n.min));
  const pctF = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 0 });
  const COUPE = "#7FE3FF";
  const N = 256;
  const nb = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  const nb1 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
  const echapper = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // ------------------------------------------------------------------ géométrie (sphère du corps)
  const rad = (d) => (d * Math.PI) / 180;
  /** Projection azimutale équidistante autour de (lat0, lon0) : (x vers l'est, y vers le nord) en km. */
  function versPlan(lat, lon, lat0, lon0, R) {
    const p = rad(lat), l = rad(lon) - rad(lon0), p0 = rad(lat0);
    const cosc = Math.sin(p0) * Math.sin(p) + Math.cos(p0) * Math.cos(p) * Math.cos(l);
    const c = Math.acos(Math.max(-1, Math.min(1, cosc)));
    const k = c < 1e-9 ? 1 : c / Math.sin(c);
    return [R * k * Math.cos(p) * Math.sin(l), R * k * (Math.cos(p0) * Math.sin(p) - Math.sin(p0) * Math.cos(p) * Math.cos(l))];
  }

  /** Centre (moyenne sur la sphère, pondérée par la surface) et taille du carré qui contient la zone. */
  function cadreZone(zone, corps) {
    const H = window.h3;
    let x = 0, y = 0, z = 0;
    zone.forEach((c) => {
      const [la, lo] = H.cellToLatLng(c);
      const w = 7 ** Math.max(0, 6 - H.getResolution(c));
      x += w * Math.cos(rad(la)) * Math.cos(rad(lo));
      y += w * Math.cos(rad(la)) * Math.sin(rad(lo));
      z += w * Math.sin(rad(la));
    });
    const lat = (Math.atan2(z, Math.hypot(x, y)) * 180) / Math.PI;
    const lon = (Math.atan2(y, x) * 180) / Math.PI;
    let demi = 0;
    zone.forEach((c) => H.cellToBoundary(c).forEach(([la, lo]) => {
      const [u, v] = versPlan(la, lo, lat, lon, RAYON_KM[corps]);
      demi = Math.max(demi, Math.abs(u), Math.abs(v));
    }));
    const taille = Math.min(800, Math.max(30, Math.ceil(demi * 2 * 1.3 / 5) * 5));
    return { lat, lon, taille };
  }

  /** Contours de cellules H3 (même résolution) en km sur le plan de la vue. */
  function contours(cellules, lat0, lon0, R) {
    const H = window.h3;
    try {
      return H.cellsToMultiPolygon(cellules, false).flatMap((poly) =>
        poly.map((anneau) => anneau.map(([la, lo]) => versPlan(la, lo, lat0, lon0, R))));
    } catch (e) {
      return [];
    }
  }

  // ------------------------------------------------------------------ chargement de three.js
  let chargement = null;
  function chargerThree() {
    if (window.THREE && window.THREE.OrbitControls) return Promise.resolve();
    if (chargement) return chargement;
    const un = (src) => new Promise((ok, ko) => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = ok;
      s.onerror = () => { s.remove(); ko(new Error(`could not load: ${src}`)); };
      document.head.appendChild(s);
    });
    const script = ([local, cdn]) => un(local).catch(() => un(cdn));
    chargement = (window.THREE ? Promise.resolve() : script(THREE_URL)).then(() => script(ORBIT_URL));
    chargement.catch(() => { chargement = null; });
    return chargement;
  }

  // ------------------------------------------------------------------ interface
  let vue = null;   // état de la vue ouverte

  function fermer() {
    if (!vue) return;
    vue.arret = true;
    viderCotes(vue);
    if (vue.obs) vue.obs.disconnect();
    if (vue.obsGraphes) vue.obsGraphes.disconnect();
    window.removeEventListener("resize", vue.redim);
    vue.el.remove();
    if (vue.retour) vue.retour.focus({ preventScroll: true });
    vue = null;
  }

  // Avant js/analogues.js (chargé après) : Échap ferme d'abord cette vue, les flèches ne changent pas de site.
  window.addEventListener("keydown", (e) => {
    if (!vue) return;
    if (e.key === "Escape") { e.stopImmediatePropagation(); e.preventDefault(); fermer(); }
    else if (e.key === "ArrowLeft" || e.key === "ArrowRight") e.stopImmediatePropagation();
  }, true);

  function ouvrir({ api, corps, zone, site, pentes }) {
    fermer();
    const cadreZ = cadreZone(zone, corps);
    const centres = [cadreZ, { lat: site.lat, lon: site.lon }];
    // Contour de la zone en km autour de son centre : le même, reporté autour du site terrestre
    const anneauxZone = contours(zoneRes6(zone), cadreZ.lat, cadreZ.lon, RAYON_KM[corps]);
    const anneauxEmpreinte = contours(site.empreinte && site.empreinte.length ? site.empreinte : [site.h3],
      site.lat, site.lon, RAYON_KM.earth);
    // Le carré contient la zone et l'empreinte (qui n'a pas tout à fait la même forme)
    const demiE = Math.max(0, ...anneauxEmpreinte.flat().map(([x, y]) => Math.max(Math.abs(x), Math.abs(y))));
    const L = Math.min(800, Math.max(cadreZ.taille, Math.ceil((demiE * 2 * 1.12) / 5) * 5));
    const traits = [anneauxZone.map((a) => ({ anneau: a })),
      anneauxZone.map((a) => ({ anneau: a })).concat(anneauxEmpreinte.map((a) => ({ anneau: a, couleur: 0xE6ECF5 })))];
    const nomZone = corps === "moon" ? "your area on the Moon" : "your area on Mars";
    const nomCorps = NOMS[corps];

    const el = document.createElement("section");
    el.className = "vue3d";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-label", "Compare the terrain");
    el.innerHTML = `
      <header class="v3-tete">
        <h2>Compare the terrain <span class="v3-verdict" id="v3-verdict"></span>
          <span class="v3-degrade" title="Inside the area: red, this kind of terrain (slope, roughness over ~1.5 km) does not exist on the other side; green, it is found there too. The same ${nb.format(L)} km square on both sides; white dots: the area judged on Earth."></span></h2>
        <div class="v3-outils">
          <div class="v3-bascule" role="group" aria-label="View">
            <button type="button" data-mode="dessus" aria-pressed="true">Top view</button>
            <button type="button" data-mode="3d" aria-pressed="false">3D</button>
          </div>
          <span class="v3-outils-3d" hidden>
            <label>Vertical exaggeration <b id="v3-ex-val">×1</b>
              <input type="range" id="v3-ex" min="1" max="20" step="1" value="1"></label>
            <span class="v3-bascule" role="group" aria-label="Surface">
              <button type="button" data-surface="image" aria-pressed="true">Image</button>
              <button type="button" data-surface="relief" aria-pressed="false">Terrain only</button>
            </span>
            <button type="button" id="v3-tourner" aria-pressed="true" title="Automatic rotation">⟳ Rotate</button>
          </span>
          <button type="button" class="v3-fermer" aria-label="Close (Escape)">×</button>
        </div>
      </header>
      <div class="v3-cotes">
        ${[corps, "earth"].map((b, i) => `
          <figure class="v3-cote" data-i="${i}">
            <figcaption>
              <span class="v3-nom" style="--c:${COULEURS[b]}">● ${i === 0 ? `${NOMS[b]} · your area` : `Earth · ${echapper(site.nom || "selected site")}`}</span>
              <span class="v3-info" id="v3-info-${i}"></span>
            </figcaption>
            <div class="v3-scene" id="v3-scene-${i}">
              <span class="v3-credit" id="v3-credit-${i}"></span>
              <div class="v3-2d"><div class="v3-carre"><canvas class="v3-carte"></canvas><canvas class="v3-calque"></canvas></div></div>
              <div class="v3-3d" hidden></div>
              <p class="v3-attente">Loading the terrain of ${i === 0 ? (corps === "moon" ? "the Moon" : "Mars") : "the Earth"}…</p>
            </div>
          </figure>`).join("")}
      </div>
      <div class="v3-graphes">
        <figure class="v3-graphe">
          <figcaption><b title="Elevation along the dotted line (a click on a map moves it), relative to the median level of each square. The percentage compares the elevation range and roughness of the whole area.">Profile</b>
            <span class="v3-score" id="v3-score-coupe"></span>
            <span class="v3-bascule" role="group" aria-label="Profile direction">
              <button type="button" data-sens="we" aria-pressed="true">west → east</button>
              <button type="button" data-sens="ns" aria-pressed="false">north → south</button>
            </span>
            <span class="v3-leg"><i style="--c:${COULEURS[corps]}"></i>${NOMS[corps]} <i style="--c:${COULEURS.earth}"></i>Earth <i class="v3-leg-zone"></i>area</span></figcaption>
          <div id="v3-coupe" class="v3-svg"></div>
        </figure>
        <figure class="v3-graphe">
          <figcaption><b id="v3-pentes-titre">Slopes</b> <span class="v3-score" id="v3-score-pentes"></span>
            <span class="v3-leg"><i style="--c:${COULEURS[corps]}"></i>${NOMS[corps]} <i style="--c:${COULEURS.earth}"></i>Earth</span></figcaption>
          <div id="v3-pentes" class="v3-svg"></div>
        </figure>
      </div>`;
    document.body.appendChild(el);
    vue = { el, cotes: [{}, {}], arret: false, exag: 1, surface: "image", tourne: true, mode: "dessus",
      sens: "we", pos: 0, donnees: [null, null], L, traits, sim: { coupe: null, pentes: null }, voirLocal: true, corps, nomCorps, pentes, retour: document.activeElement };
    const V = vue;
    el.querySelector(".v3-fermer").addEventListener("click", fermer);
    el.querySelector(".v3-fermer").focus({ preventScroll: true });

    const demandes = [corps, "earth"].map((b, i) => fetch(`${api}/api/relief?body=${b}&lat=${centres[i].lat.toFixed(4)}` +
      `&lon=${centres[i].lon.toFixed(4)}&size_km=${L}&n=${N}`)
      .then(async (r) => {
        const d = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(d.detail || `erreur ${r.status}`);
        return decoder(d);
      }).then((d) => d, (e) => e));

    Promise.all(demandes).then((donnees) => {
      if (V.arret) return;
      V.donnees = donnees.map((d) => (d instanceof Error ? null : d));
      donnees.forEach((d, i) => {
        const attente = el.querySelector(`#v3-scene-${i} .v3-attente`);
        if (d instanceof Error) {
          attente.textContent = `Terrain unavailable: ${d.message}`;
          attente.classList.add("v3-erreur");
          return;
        }
        attente.remove();
        const mer = d.eau ? d.eau.reduce((a, v) => a + v, 0) / d.eau.length : 0;
        el.querySelector(`#v3-info-${i}`).textContent = `elevation range ${nb.format(d.relief_p5_p95)} m · elevation ` +
          `${nb.format(d.min)} to ${nb.format(d.max)} m` + (mer >= 0.01 ? ` · sea ${nb.format(100 * mer)}% of the square` : "");
      });
      const ok = V.donnees.filter(Boolean);
      // Exagération de départ (3D) : que le plus fort relief fasse ~1/12 du côté
      const r = Math.max(0.0005, ...ok.map((d) => (d.relief_p5_p95 || 0) / 1000 / L));
      V.exag = Math.max(1, Math.min(20, Math.round(1 / 12 / r)));
      el.querySelector("#v3-ex").value = V.exag;
      el.querySelector("#v3-ex-val").textContent = `×${V.exag}`;
      V.donnees.forEach((d, i) => {
        if (!d) return;
        el.querySelector(`#v3-credit-${i}`).textContent = { mars: "MOLA · NASA Trek", moon: "LOLA · NASA Trek", earth: "Copernicus · Esri" }[d.body];
        el.querySelector(`#v3-credit-${i}`).title = `Terrain: ${d.source}${d.texture_credit ? `; image: ${d.texture_credit}` : ""}`;
      });
      V.masque = masqueZone(N, L, traits[0]);
      V.local = ressemblanceLocale(V.donnees, V.masque);
      V.mesures = V.donnees.map((d) => (d ? mesuresZone(d, V.masque) : null));
      const [m0, m1] = V.mesures;
      V.sim.coupe = m0 && m1 ? 0.5 * rapport(m0.amp, m1.amp, 10) + 0.5 * rapport(m0.rug, m1.rug, 0.5) : null;
      dessinerCoupe(V);
      dessinerPentes(V);
      dessinerCartes(V);
    });

    // Interactions
    el.querySelectorAll("[data-mode]").forEach((bt) => bt.addEventListener("click", () => choisirMode(V, bt.dataset.mode)));
    el.querySelectorAll("[data-sens]").forEach((bt) => bt.addEventListener("click", () => {
      V.sens = bt.dataset.sens;
      V.pos = 0;
      el.querySelectorAll("[data-sens]").forEach((x) => x.setAttribute("aria-pressed", String(x === bt)));
      dessinerCalques(V);
      dessinerCoupe(V);
    }));
    el.querySelectorAll(".v3-calque").forEach((cv) => cv.addEventListener("click", (e) => {
      const b = cv.getBoundingClientRect();
      const x = ((e.clientX - b.left) / b.width - 0.5) * L, y = (0.5 - (e.clientY - b.top) / b.height) * L;
      V.pos = V.sens === "we" ? y : x;
      dessinerCalques(V);
      dessinerCoupe(V);
    }));
    el.querySelector("#v3-ex").addEventListener("input", (e) => {
      V.exag = +e.target.value;
      el.querySelector("#v3-ex-val").textContent = `×${V.exag}`;
      V.cotes.forEach((c) => c.hauteurs && poserHauteurs(c, V.exag));
      rendre(V);
    });
    el.querySelectorAll("[data-surface]").forEach((bt) => bt.addEventListener("click", () => {
      V.surface = bt.dataset.surface;
      el.querySelectorAll("[data-surface]").forEach((x) => x.setAttribute("aria-pressed", String(x === bt)));
      V.cotes.forEach((c) => c.mesh && appliquerSurface(c, V.surface));
      rendre(V);
    }));
    el.querySelector("#v3-tourner").addEventListener("click", (e) => {
      V.tourne = !V.tourne;
      e.currentTarget.setAttribute("aria-pressed", String(V.tourne));
      if (V.tourne) animer(V);
    });
    V.redim = () => {
      if (V.mode === "dessus") dessinerCartes(V);
      else { V.cotes.forEach((c) => c.renderer && dimensionner(c)); rendre(V); }
    };
    window.addEventListener("resize", V.redim);
    // La hauteur des cartes change quand les graphiques se remplissent : on recadre les carrés
    if (window.ResizeObserver) {
      V.obs = new ResizeObserver(() => { if (V.mode === "dessus" && !V.arret) dessinerCartes(V); });
      el.querySelectorAll(".v3-scene").forEach((x) => V.obs.observe(x));
      V.obsGraphes = new ResizeObserver(() => { if (!V.arret && V.donnees.some(Boolean)) { dessinerCoupe(V); dessinerPentes(V); } });
      el.querySelectorAll(".v3-svg").forEach((x) => V.obsGraphes.observe(x));
    }
  }

  function decoder(d) {
    const octets = (b64) => Uint8Array.from(atob(b64), (ch) => ch.charCodeAt(0));
    const h16 = new Int16Array(octets(d.heights_i16).buffer);
    const tri = Float32Array.from(h16).sort();
    return { ...d, h16, tri, mediane: tri[Math.floor(tri.length / 2)], eau: d.water_u8 ? octets(d.water_u8) : null };
  }

  function choisirMode(V, mode) {
    if (V.mode === mode) return;
    V.mode = mode;
    const el = V.el;
    el.querySelectorAll("[data-mode]").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.mode === mode)));
    el.querySelector(".v3-outils-3d").hidden = mode !== "3d";
    el.querySelectorAll(".v3-2d").forEach((x) => { x.hidden = mode !== "dessus"; });
    el.querySelectorAll(".v3-3d").forEach((x) => { x.hidden = mode !== "3d"; });
    if (mode === "dessus") { dessinerCartes(V); return; }
    if (V.cotes.some((c) => c.renderer)) {
      V.cotes.forEach((c) => c.renderer && dimensionner(c));
      rendre(V);
      if (V.tourne) animer(V);
      return;
    }
    el.querySelectorAll(".v3-3d").forEach((x) => { x.innerHTML = `<p class="v3-attente">Loading the 3D view…</p>`; });
    chargerThree().then(() => {
      if (V.arret) return;
      V.donnees.forEach((d, i) => {
        const conteneur = el.querySelector(`#v3-scene-${i} .v3-3d`);
        if (d) construire(V, i, conteneur, d, V.L, V.traits[i]);
        else conteneur.innerHTML = "";
      });
      lier(V);
    }, () => {
      el.querySelectorAll(".v3-3d .v3-attente").forEach((p) => {
        p.textContent = "The 3D library (three.js) could not be loaded: check the Internet connection.";
        p.classList.add("v3-erreur");
      });
    });
  }

  /** Libère les maquettes 3D (WebGL, géométries, contrôles). */
  function viderCotes(V) {
    V.cotes.forEach((c) => {
      if (c.ctl) c.ctl.dispose();
      if (c.renderer) { c.renderer.dispose(); c.renderer.forceContextLoss(); c.renderer.domElement.remove(); }
      if (c.scene) c.scene.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) { if (o.material.map) o.material.map.dispose(); o.material.dispose(); } });
    });
    V.cotes = [{}, {}];
  }

  function zoneRes6(zone) {
    const H = window.h3;
    try { return H.uncompactCells(zone, 6); } catch (e) { return zone; }
  }

  // ------------------------------------------------------------------ cartes vues de dessus
  const RAMPE = [[0, [38, 44, 66]], [0.3, [96, 84, 78]], [0.6, [176, 138, 98]], [0.85, [222, 196, 150]], [1, [246, 236, 214]]];
  const MER = [29, 78, 122];
  const EXAG_OMBRE = 4;          // même ombrage des deux côtés

  function rampe(t) {
    for (let j = 1; j < RAMPE.length; j++) {
      if (t <= RAMPE[j][0]) {
        const [t0, a] = RAMPE[j - 1], [t1, b] = RAMPE[j];
        const f = (t - t0) / (t1 - t0);
        return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
      }
    }
    return RAMPE[RAMPE.length - 1][1];
  }

  function dessinerCartes(V) {
    V.donnees.forEach((d, i) => {
      const scene = V.el.querySelector(`#v3-scene-${i}`);
      const carre = scene.querySelector(".v3-carre");
      const cote = Math.max(50, Math.min(scene.clientWidth, scene.clientHeight) - 8);
      carre.style.width = carre.style.height = `${cote}px`;
      if (!d) return;
      const cv = scene.querySelector(".v3-carte");
      if (!cv.dataset.fait) {
        const n = d.n, g = d.grid_m, h = d.h16;
        cv.width = cv.height = n;
        const ctx = cv.getContext("2d");
        const img = ctx.createImageData(n, n);
        const bas = d.tri[Math.floor(d.tri.length * 0.02)], haut = d.tri[Math.floor(d.tri.length * 0.98)];
        const Lx = -0.5, Ly = 0.5, Lz = Math.SQRT1_2;
        for (let r = 0; r < n; r++) {
          for (let q = 0; q < n; q++) {
            const k = r * n + q;
            let rgb;
            if (d.eau && d.eau[k]) rgb = MER;
            else {
              const dx = (h[r * n + Math.min(n - 1, q + 1)] - h[r * n + Math.max(0, q - 1)]) / (2 * g) * EXAG_OMBRE;
              const dy = (h[Math.max(0, r - 1) * n + q] - h[Math.min(n - 1, r + 1) * n + q]) / (2 * g) * EXAG_OMBRE;
              const nz = 1 / Math.sqrt(dx * dx + dy * dy + 1);
              const ombre = Math.max(0, (-dx * Lx - dy * Ly + Lz) * nz);
              const c = rampe(Math.max(0, Math.min(1, (h[k] - bas) / Math.max(1, haut - bas))));
              const f = 0.3 + 0.85 * ombre;
              rgb = [c[0] * f, c[1] * f, c[2] * f];
            }
            img.data[k * 4] = rgb[0]; img.data[k * 4 + 1] = rgb[1]; img.data[k * 4 + 2] = rgb[2]; img.data[k * 4 + 3] = 255;
          }
        }
        ctx.putImageData(img, 0, 0);
        cv.dataset.fait = "1";
      }
    });
    dessinerCalques(V);
  }

  /** Zone (couleur du niveau), empreinte (pointillé), ligne de coupe et barre d'échelle, à la résolution de l'écran. */
  function dessinerCalques(V) {
    const L = V.L;
    V.donnees.forEach((d, i) => {
      const cv = V.el.querySelector(`#v3-scene-${i} .v3-calque`);
      const b = cv.getBoundingClientRect();
      if (!b.width) return;
      const dpr = window.devicePixelRatio || 1;
      cv.width = Math.round(b.width * dpr);
      cv.height = Math.round(b.height * dpr);
      const S = cv.width;
      const ctx = cv.getContext("2d");
      ctx.clearRect(0, 0, S, S);
      const px = (x) => ((x + L / 2) / L) * S, py = (y) => ((L / 2 - y) / L) * S;
      const chemin = (liste) => {
        ctx.beginPath();
        liste.forEach(({ anneau }) => {
          anneau.forEach(([x, y], j) => (j ? ctx.lineTo(px(x), py(y)) : ctx.moveTo(px(x), py(y))));
          ctx.closePath();
        });
      };
      // La zone, teintée selon la ressemblance du relief (blanche tant qu'elle n'est pas calculée)
      const nv = niveau(V.sim.total);
      if (V.voirLocal && V.local && V.local[i]) {
        ctx.imageSmoothingEnabled = true;
        ctx.drawImage(imageLocale(V, i), 0, 0, S, S);
      }
      chemin(V.traits[i].filter((t) => !t.couleur));
      if (nv !== NEUTRE && !(V.voirLocal && V.local && V.local[i])) {
        ctx.fillStyle = nv.couleur + "3A";
        ctx.fill("evenodd");
      }
      ctx.strokeStyle = nv.couleur;
      ctx.lineWidth = 2.5 * dpr;
      ctx.stroke();
      // L'empreinte jugée sur Terre
      const empreinte = V.traits[i].filter((t) => t.couleur);
      if (empreinte.length) {
        chemin(empreinte);
        ctx.strokeStyle = EMPREINTE;
        ctx.lineWidth = 1.6 * dpr;
        ctx.setLineDash([3 * dpr, 3 * dpr]);
        ctx.stroke();
        ctx.setLineDash([]);
      }
      // Coupe
      ctx.save();
      ctx.setLineDash([6 * dpr, 4 * dpr]);
      ctx.strokeStyle = COUPE;
      ctx.lineWidth = 2 * dpr;
      ctx.beginPath();
      if (V.sens === "we") { ctx.moveTo(0, py(V.pos)); ctx.lineTo(S, py(V.pos)); }
      else { ctx.moveTo(px(V.pos), 0); ctx.lineTo(px(V.pos), S); }
      ctx.stroke();
      ctx.restore();
      ctx.font = `${600} ${12 * dpr}px Archivo, sans-serif`;
      ctx.fillStyle = COUPE;
      if (V.sens === "we") { ctx.fillText("W", 4 * dpr, py(V.pos) - 5 * dpr); ctx.fillText("E", S - 12 * dpr, py(V.pos) - 5 * dpr); }
      else { ctx.fillText("N", px(V.pos) + 5 * dpr, 14 * dpr); ctx.fillText("S", px(V.pos) + 5 * dpr, S - 6 * dpr); }
      // Barre d'échelle
      const km = joli(L / 5);
      const lg = (km / L) * S;
      ctx.fillStyle = "rgba(8,17,32,0.7)";
      ctx.fillRect(8 * dpr, S - 30 * dpr, lg + 16 * dpr, 22 * dpr);
      ctx.fillStyle = "#fff";
      ctx.fillRect(16 * dpr, S - 14 * dpr, lg, 3 * dpr);
      ctx.font = `${11 * dpr}px Archivo, sans-serif`;
      ctx.fillText(`${nb.format(km)} km`, 16 * dpr, S - 18 * dpr);
    });
  }

  function joli(x) {
    const p = 10 ** Math.floor(Math.log10(x));
    return [1, 2, 5, 10].map((m) => m * p).reduce((a, b) => (Math.abs(b - x) < Math.abs(a - x) ? b : a));
  }

  function graduations(min, max, n = 5) {
    const pas = joli((max - min) / n) || 1;
    const t = [];
    for (let v = Math.ceil(min / pas) * pas; v <= max + 1e-9; v += pas) t.push(+v.toFixed(6));
    return t;
  }

  /** Le point (x, y) en km est-il dans la zone (contours blancs, règle pair-impair) ? */
  function dansZone(anneaux, x, y) {
    let dedans = false;
    anneaux.forEach(({ anneau }) => {
      for (let i = 0, j = anneau.length - 1; i < anneau.length; j = i++) {
        const [xi, yi] = anneau[i], [xj, yj] = anneau[j];
        if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) dedans = !dedans;
      }
    });
    return dedans;
  }

  // ------------------------------------------------------------------ coupe
  function dessinerCoupe(V) {
    const boite = V.el.querySelector("#v3-coupe");
    const L = V.L;
    const series = V.donnees.map((d) => {
      if (!d) return null;
      const n = d.n;
      const fixe = Math.round(V.sens === "we" ? ((L / 2 - V.pos) / L) * (n - 1) : ((V.pos + L / 2) / L) * (n - 1));
      return Array.from({ length: n }, (_, j) => {
        const k = V.sens === "we" ? fixe * n + j : j * n + fixe;
        return { s: (j / (n - 1)) * L, z: d.h16[k] - d.mediane, eau: d.eau ? d.eau[k] === 1 : false };
      });
    });
    const toutes = series.filter(Boolean).flat();
    if (!toutes.length) { boite.innerHTML = ""; return; }
    let zmin = Math.min(...toutes.map((p) => p.z)), zmax = Math.max(...toutes.map((p) => p.z));
    const marge = Math.max(20, (zmax - zmin) * 0.1);
    zmin -= marge; zmax += marge;
    const sc = V.el.querySelector("#v3-score-coupe");
    sc.innerHTML = V.sim.coupe == null ? "" : `<span style="--c:${niveau(V.sim.coupe).couleur}">${pctF.format(V.sim.coupe)}</span>`;
    sc.title = V.sim.coupe == null ? "" : `Whole area: elevation range ${nb.format(V.mesures[0].amp)} m versus ${nb.format(V.mesures[1].amp)} m, ` +
      `roughness ${nb1.format(V.mesures[0].rug)} m versus ${nb1.format(V.mesures[1].rug)} m from one point to the next.`;
    const W = Math.max(300, boite.clientWidth || 640), Hh = Math.max(110, boite.clientHeight || 200), g = 46, dr = 10, h = 10, b = 22;
    const X = (s) => g + (s / L) * (W - g - dr), Y = (z) => h + ((zmax - z) / (zmax - zmin)) * (Hh - h - b);
    // Bande : la partie de la coupe qui traverse la zone (contour blanc)
    // Ressemblance de la coupe, sur la partie dans la zone : dénivelé (5e-95e centile) et rugosité (|Δz| moyen)
    const dedansJ = series[0] ? series[0].map((p) => dansZone(V.traits[0], ...(V.sens === "we" ? [p.s - L / 2, V.pos] : [V.pos, L / 2 - p.s]))) : [];
    const mesures = series.map((pts) => {
      if (!pts) return null;
      const z = pts.filter((p, j) => dedansJ[j] && !p.eau).map((p) => p.z);
      if (z.length < 8) return null;
      const t = [...z].sort((a, b) => a - b);
      let rug = 0;
      for (let j = 1; j < z.length; j++) rug += Math.abs(z[j] - z[j - 1]);
      return { amp: t[Math.floor(t.length * 0.95)] - t[Math.floor(t.length * 0.05)], rug: rug / (z.length - 1) };
    });
    let bandes = "", debut = null;
    const pas = L / 200;
    for (let s = 0; s <= L + 1e-9; s += pas) {
      const [x, y] = V.sens === "we" ? [s - L / 2, V.pos] : [V.pos, L / 2 - s];
      const dedans = dansZone(V.traits[0], x, y);
      if (dedans && debut === null) debut = s;
      if ((!dedans || s + pas > L) && debut !== null) {
        bandes += `<rect x="${X(debut)}" y="${h}" width="${Math.max(1, X(s) - X(debut))}" height="${Hh - h - b}" fill="rgba(255,255,255,0.07)"/>`;
        debut = null;
      }
    }
    const tracer = (pts, couleur) => {
      let terre = "", mer = "";
      pts.forEach((p, j) => {
        const seg = `${j && pts[j - 1].eau === p.eau ? "L" : "M"}${X(p.s).toFixed(1)},${Y(p.z).toFixed(1)}`;
        if (p.eau) mer += seg; else terre += seg;
      });
      return `<path d="${terre}" fill="none" stroke="${couleur}" stroke-width="2"/>` +
        (mer ? `<path d="${mer}" fill="none" stroke="#3E8EDE" stroke-width="2" stroke-dasharray="4 3"/>` : "");
    };
    const gx = graduations(0, L), gy = graduations(zmin, zmax, 4);
    boite.innerHTML = `<svg viewBox="0 0 ${W} ${Hh}" width="${W}" height="${Hh}" role="img" aria-label="Terrain profile of both areas">
      ${bandes}
      ${gy.map((z) => `<line x1="${g}" x2="${W - dr}" y1="${Y(z)}" y2="${Y(z)}" stroke="rgba(255,255,255,0.08)"/>
        <text x="${g - 6}" y="${Y(z) + 4}" text-anchor="end">${z > 0 ? "+" : ""}${nb.format(z)} m</text>`).join("")}
      ${gx.map((s, j) => `<text x="${X(s)}" y="${Hh - 6}" text-anchor="${j === gx.length - 1 && s > L * 0.95 ? "end" : "middle"}">${nb.format(s)} km</text>`).join("")}
      ${series[0] ? tracer(series[0], COULEURS[V.corps]) : ""}
      ${series[1] ? tracer(series[1], COULEURS.earth) : ""}
    </svg>
`;
    majVerdict(V);
  }

  const rapport = (a, b, plancher) => Math.min(a + plancher, b + plancher) / Math.max(a + plancher, b + plancher);

  /** Dénivelé (5e-95e centile) et rugosité (|Δz| moyen entre points voisins, lignes et colonnes) dans la zone. */
  function mesuresZone(d, masque) {
    const n = d.n, h = d.h16, eau = d.eau;
    const z = [];
    let somme = 0, paires = 0;
    const garde = (k) => masque[k] && !(eau && eau[k]);
    for (let r = 0; r < n; r++) {
      for (let q = 0; q < n; q++) {
        const k = r * n + q;
        if (!garde(k)) continue;
        z.push(h[k]);
        if (q + 1 < n && garde(k + 1)) { somme += Math.abs(h[k + 1] - h[k]); paires++; }
        if (r + 1 < n && garde(k + n)) { somme += Math.abs(h[k + n] - h[k]); paires++; }
      }
    }
    if (z.length < 30 || !paires) return null;
    z.sort((a, b) => a - b);
    return { amp: z[Math.floor(z.length * 0.95)] - z[Math.floor(z.length * 0.05)], rug: somme / paires };
  }

  // ------------------------------------------------------------------ ressemblance par endroit (dégradé)
  /** Pente (°) et rugosité (écart-type de l'altitude sur 5 x 5 points, ~1,5 km pour 80 km) de chaque point. */
  function caracteres(d, masque) {
    const n = d.n, h = d.h16, g = d.grid_m, R = 2;
    const pente = new Float32Array(n * n).fill(NaN), rug = new Float32Array(n * n).fill(NaN);
    for (let r = 0; r < n; r++) {
      for (let q = 0; q < n; q++) {
        const k = r * n + q;
        if (!masque[k] || (d.eau && d.eau[k])) continue;
        const qa = Math.max(0, q - 1), qb = Math.min(n - 1, q + 1), ra = Math.max(0, r - 1), rb = Math.min(n - 1, r + 1);
        const dx = (h[r * n + qb] - h[r * n + qa]) / ((qb - qa) * g), dy = (h[ra * n + q] - h[rb * n + q]) / ((rb - ra) * g);
        pente[k] = (Math.atan(Math.hypot(dx, dy)) * 180) / Math.PI;
        let s = 0, s2 = 0, m = 0;
        for (let i = Math.max(0, r - R); i <= Math.min(n - 1, r + R); i++) {
          for (let j = Math.max(0, q - R); j <= Math.min(n - 1, q + R); j++) {
            const v = h[i * n + j]; s += v; s2 += v * v; m++;
          }
        }
        rug[k] = Math.sqrt(Math.max(0, s2 / m - (s / m) ** 2));
      }
    }
    return { pente, rug };
  }

  /** Pour chaque côté, ressemblance (0 à 1) de chaque point de la zone au terrain de l'autre zone, lissée.
   *  Chaque point a un « type de terrain » : sa case dans un histogramme 2D (pente, rugosité ; échelles log, 10 x 10).
   *  Ressemblance = part de ce type de terrain dans l'autre zone / sa part dans cette zone, plafonnée à 1 : deux
   *  zones identiques sont vertes partout ; un terrain fréquent ici mais rare (ou absent) en face tire vers le rouge. */
  function ressemblanceLocale(donnees, masque) {
    if (!donnees[0] || !donnees[1]) return null;
    const n = donnees[0].n, B = 10;
    const car = donnees.map((d) => caracteres(d, masque));
    const lp = (v) => Math.log10(v + 0.05), lr = (v) => Math.log10(v + 0.5);
    const tous = (f, cle) => car.flatMap((c) => Array.from(c[cle]).filter(Number.isFinite).map(f)).sort((x, y) => x - y);
    const vp = tous(lp, "pente"), vr = tous(lr, "rug");
    if (vp.length < 60) return null;
    const lim = (v) => [v[Math.floor(v.length * 0.01)], v[Math.floor(v.length * 0.99)] + 1e-6];
    const [p0, p1] = lim(vp), [r0, r1] = lim(vr);
    const caseDe = (pe, ru) => {
      const i = Math.max(0, Math.min(B - 1, Math.floor(((lp(pe) - p0) / (p1 - p0)) * B)));
      const j = Math.max(0, Math.min(B - 1, Math.floor(((lr(ru) - r0) / (r1 - r0)) * B)));
      return i * B + j;
    };
    // Histogrammes normalisés, adoucis par les cases voisines (évite les cases vides par hasard)
    const histos = car.map((c) => {
      const h = new Float64Array(B * B);
      let tot = 0;
      for (let k = 0; k < n * n; k++) if (Number.isFinite(c.pente[k])) { h[caseDe(c.pente[k], c.rug[k])] += 1; tot++; }
      const d = new Float64Array(B * B);
      for (let i = 0; i < B; i++) for (let j = 0; j < B; j++) {
        let s = 0, w = 0;
        for (let di = -1; di <= 1; di++) for (let dj = -1; dj <= 1; dj++) {
          const ii = i + di, jj = j + dj;
          if (ii < 0 || jj < 0 || ii >= B || jj >= B) continue;
          const p = di === 0 && dj === 0 ? 1 : 0.35;
          s += p * h[ii * B + jj]; w += p;
        }
        d[i * B + j] = s / w / Math.max(1, tot);
      }
      return d;
    });
    return [0, 1].map((i) => {
      const c = car[i], ici = histos[i], face = histos[1 - i];
      const brut = new Float32Array(n * n).fill(NaN);
      for (let k = 0; k < n * n; k++) {
        if (!Number.isFinite(c.pente[k])) continue;
        const b = caseDe(c.pente[k], c.rug[k]);
        brut[k] = Math.min(1, (face[b] + 1e-4) / (ici[b] + 1e-4));
      }
      return lisser(brut, n, 3);
    });
  }

  /** Moyenne glissante (fenêtre 2R + 1) sur les seuls points définis, en deux passes séparables. */
  function lisser(x, n, R) {
    const passe = (src, horizontal) => {
      const out = new Float32Array(n * n).fill(NaN);
      for (let r = 0; r < n; r++) {
        for (let q = 0; q < n; q++) {
          const k = r * n + q;
          if (!Number.isFinite(x[k])) continue;
          let s = 0, m = 0;
          for (let t = -R; t <= R; t++) {
            const rr = horizontal ? r : r + t, qq = horizontal ? q + t : q;
            if (rr < 0 || qq < 0 || rr >= n || qq >= n) continue;
            const v = src[rr * n + qq];
            if (Number.isFinite(v)) { s += v; m++; }
          }
          out[k] = s / m;
        }
      }
      return out;
    };
    return passe(passe(x, true), false);
  }

  const DEGRADE = [[0, [242, 84, 91]], [0.4, [242, 193, 78]], [0.6, [185, 224, 90]], [1, [61, 220, 151]]];
  function couleurDegrade(t) {
    for (let j = 1; j < DEGRADE.length; j++) {
      if (t <= DEGRADE[j][0]) {
        const [t0, a] = DEGRADE[j - 1], [t1, b] = DEGRADE[j], f = (t - t0) / (t1 - t0);
        return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
      }
    }
    return DEGRADE[DEGRADE.length - 1][1];
  }

  /** Image n x n du dégradé (transparente hors de la zone), gardée pour les redessins. */
  function imageLocale(V, i) {
    V.images = V.images || [];
    if (V.images[i]) return V.images[i];
    const x = V.local[i], n = Math.sqrt(x.length);
    const cv = document.createElement("canvas");
    cv.width = cv.height = n;
    const ctx = cv.getContext("2d");
    const img = ctx.createImageData(n, n);
    for (let k = 0; k < n * n; k++) {
      if (!Number.isFinite(x[k])) continue;
      const c = couleurDegrade(Math.max(0, Math.min(1, x[k])));
      img.data[k * 4] = c[0]; img.data[k * 4 + 1] = c[1]; img.data[k * 4 + 2] = c[2]; img.data[k * 4 + 3] = 125;
    }
    ctx.putImageData(img, 0, 0);
    return (V.images[i] = cv);
  }

  // ------------------------------------------------------------------ verdict (couleur de la zone)
  function majVerdict(V) {
    const vals = [V.sim.coupe, V.sim.pentes].filter((x) => x != null);
    const total = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
    const change = niveau(total) !== niveau(V.sim.total);
    V.sim.total = total;
    const nv = niveau(total);
    V.el.querySelector("#v3-verdict").innerHTML = total == null ? "" :
      `<span style="--c:${nv.couleur}">Terrain: ${nv.nom.toLowerCase()} · ${pctF.format(total)}</span>`;
    V.el.querySelector("#v3-verdict").title = "Average of the profile and slope similarities; the color of the area on the maps";
    dessinerCalques(V);
    if (change) V.cotes.forEach((c) => { if (c.mesh) { c.couleurZone = nv.couleur; teinterZone(c, V); poserHauteurs(c, V.exag); } });
    rendre(V);
  }

  // ------------------------------------------------------------------ pentes
  const CLASSES = [[0, 2, "< 2°"], [2, 5, "2 to 5°"], [5, 10, "5 to 10°"], [10, 20, "10 to 20°"], [20, 90, "> 20°"]];

  /** Part du terrain de pente inférieure à t, d'après les 9 déciles (interpolation linéaire). */
  function sousDeciles(d, t) {
    const xs = [0, ...d, Math.max(d[8] * 1.6, d[8] + 3)];
    const ps = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1];
    if (t <= 0) return 0;
    if (t >= xs[10]) return 1;
    for (let j = 0; j < 10; j++) {
      if (t <= xs[j + 1]) return ps[j] + ((ps[j + 1] - ps[j]) * (t - xs[j])) / Math.max(1e-9, xs[j + 1] - xs[j]);
    }
    return 1;
  }

  function partsGrille(d) {
    const n = d.n, g = d.grid_m, h = d.h16, comptes = CLASSES.map(() => 0);
    let total = 0;
    for (let r = 1; r < n - 1; r++) {
      for (let q = 1; q < n - 1; q++) {
        const k = r * n + q;
        if (d.eau && d.eau[k]) continue;
        const dx = (h[k + 1] - h[k - 1]) / (2 * g), dy = (h[k - n] - h[k + n]) / (2 * g);
        const p = (Math.atan(Math.hypot(dx, dy)) * 180) / Math.PI;
        comptes[CLASSES.findIndex(([a, b]) => p >= a && p < b)] += 1;
        total += 1;
      }
    }
    return comptes.map((c) => c / Math.max(1, total));
  }

  function dessinerPentes(V) {
    const boite = V.el.querySelector("#v3-pentes");
    const titre = V.el.querySelector("#v3-pentes-titre");
    const ok = (x) => Array.isArray(x) && x.length === 9 && x.every((v) => v != null && Number.isFinite(v));
    let parts;
    if (V.pentes && ok(V.pentes.zone) && ok(V.pentes.site)) {
      parts = [V.pentes.zone, V.pentes.site].map((d) => CLASSES.map(([a, b]) => sousDeciles(d, b) - sousDeciles(d, a)));
      titre.title = "Share of the ground in each slope class, measured at 500 m: this is what the Terrain criterion compares.";
    } else {
      parts = V.donnees.map((d) => (d ? partsGrille(d) : null));
      titre.title = `Share of the ground in each slope class, computed on the ${nb.format(V.L * 1000 / (N - 1))} m grid.`;
    }
    V.sim.pentes = parts[0] && parts[1] ? parts[0].reduce((a, p, j) => a + Math.min(p, parts[1][j]), 0) : null;
    V.el.querySelector("#v3-score-pentes").innerHTML = V.sim.pentes == null ? "" :
      `<span style="--c:${niveau(V.sim.pentes).couleur}" title="Overlap of the two distributions">${pctF.format(V.sim.pentes)}</span>`;
    const W = Math.max(300, boite.clientWidth || 640), Hh = Math.max(110, boite.clientHeight || 200), g = 20, b = 22, h = 16;
    const max = Math.max(0.2, ...parts.filter(Boolean).flat());
    const Y = (p) => h + (1 - p / max) * (Hh - h - b);
    const larg = (W - g - 10) / CLASSES.length;
    const barres = CLASSES.map(([, , nom], j) => {
      const x0 = g + j * larg + larg * 0.18, lb = larg * 0.3;
      return [0, 1].map((s) => {
        const p = parts[s] ? parts[s][j] : null;
        if (p == null) return "";
        const x = x0 + s * (lb + 4);
        return `<rect x="${x}" y="${Y(p)}" width="${lb}" height="${Y(0) - Y(p)}" rx="2" fill="${s ? COULEURS.earth : COULEURS[V.corps]}"/>
          <text x="${x + lb / 2}" y="${Y(p) - 4}" text-anchor="middle">${nb.format(100 * p)}%</text>`;
      }).join("") + `<text x="${g + j * larg + larg / 2}" y="${Hh - 8}" text-anchor="middle">${nom}</text>`;
    }).join("");
    boite.innerHTML = `<svg viewBox="0 0 ${W} ${Hh}" width="${W}" height="${Hh}" role="img" aria-label="Slope distribution of both areas">
      <line x1="${g}" x2="${W - 10}" y1="${Y(0)}" y2="${Y(0)}" stroke="rgba(255,255,255,0.25)"/>
      ${barres}
    </svg>
`;
    majVerdict(V);
  }

  // ------------------------------------------------------------------ une maquette 3D
  function construire(V, i, conteneur, d, L, traits) {
    const T = window.THREE;
    conteneur.innerHTML = "";
    const renderer = new T.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.outputEncoding = T.sRGBEncoding;
    conteneur.appendChild(renderer.domElement);
    const scene = new T.Scene();
    const camera = new T.PerspectiveCamera(38, 1, L / 200, L * 20);
    scene.add(new T.HemisphereLight(0xffffff, 0x3a3a46, 0.55));
    const soleil = new T.DirectionalLight(0xffffff, 0.95);
    soleil.position.set(-L, L * 0.9, -L * 0.6);   // soleil au nord-ouest, comme sur les cartes ombrées
    scene.add(soleil);

    const n = d.n, h16 = d.h16, tri = d.tri;
    const hauteurs = Float32Array.from(h16, (v) => (v - d.mediane) / 1000);   // km, autour de la médiane
    const geo = new T.PlaneGeometry(L, L, n - 1, n - 1);
    geo.rotateX(-Math.PI / 2);                                              // ligne 0 au nord (-z)
    const couleurs = new Float32Array(n * n * 3);
    const bas = tri[Math.floor(tri.length * 0.02)], haut = tri[Math.floor(tri.length * 0.98)];
    h16.forEach((v, k) => {
      // même rampe que les cartes (couleurs sRGB converties en linéaire : le rendu les réencode)
      const c = d.eau && d.eau[k] ? MER : rampe(Math.max(0, Math.min(1, (v - bas) / Math.max(1, haut - bas))));
      couleurs[k * 3] = (c[0] / 255) ** 2.2;
      couleurs[k * 3 + 1] = (c[1] / 255) ** 2.2;
      couleurs[k * 3 + 2] = (c[2] / 255) ** 2.2;
    });
    geo.setAttribute("color", new T.BufferAttribute(couleurs, 3));
    const materiau = new T.MeshStandardMaterial({ roughness: 1, metalness: 0, vertexColors: true });
    const mesh = new T.Mesh(geo, materiau);
    scene.add(mesh);

    // Socle : quatre parois sous les bords, pour l'effet maquette
    const socle = new T.Mesh(new T.BufferGeometry(), new T.MeshBasicMaterial({ color: new T.Color(0x263042).convertSRGBToLinear(), side: T.DoubleSide }));
    scene.add(socle);
    const contour = new T.Group();
    scene.add(contour);

    const c = { renderer, scene, camera, mesh, socle, contour, conteneur, hauteurs, n, L, traits, texture: null,
      couleurZone: V.sim.total == null ? null : niveau(V.sim.total).couleur };
    V.cotes[i] = c;
    // Voile coloré sur la zone : les triangles de la grille dont les trois sommets sont dans la zone, sur la même
    // géométrie (il suit l'exagération du relief)
    const masque = masqueZone(n, L, traits.filter((t) => !t.couleur));
    const indices = [];
    for (let r = 0; r < n - 1; r++) {
      for (let q = 0; q < n - 1; q++) {
        const a = r * n + q, b = a + 1, e = a + n, f = e + 1;
        if (masque[a] && masque[b] && masque[e]) indices.push(a, e, b);
        if (masque[b] && masque[e] && masque[f]) indices.push(e, f, b);
      }
    }
    const geoVoile = new T.BufferGeometry();
    geoVoile.setAttribute("position", geo.attributes.position);
    geoVoile.setIndex(indices);
    if (V.local && V.local[i]) {
      const cols = new Float32Array(n * n * 3);
      V.local[i].forEach((v, k) => {
        if (!Number.isFinite(v)) return;
        const col = couleurDegrade(Math.max(0, Math.min(1, v)));
        cols[k * 3] = (col[0] / 255) ** 2.2; cols[k * 3 + 1] = (col[1] / 255) ** 2.2; cols[k * 3 + 2] = (col[2] / 255) ** 2.2;
      });
      geoVoile.setAttribute("color", new T.BufferAttribute(cols, 3));
      c.local = true;
    }
    c.voile = new T.Mesh(geoVoile, new T.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.3,
      depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
    c.voile.renderOrder = 1;
    c.voile.frustumCulled = false;                   // géométrie partagée : sa sphère englobante n'est pas tenue à jour
    scene.add(c.voile);
    teinterZone(c, V);
    if (d.texture) {
      new T.TextureLoader().load(d.texture, (tex) => {
        tex.encoding = T.sRGBEncoding;
        tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
        c.texture = tex;
        appliquerSurface(c, V.surface);
        rendre(V);
      });
    }
    poserHauteurs(c, V.exag);
    dimensionner(c);
    const k = Math.max(1, 1.2 / camera.aspect);      // panneau étroit : on recule pour voir tout le carré
    camera.position.set(L * 0.08 * k, L * 0.78 * k, L * 1.3 * k);
  }

  function teinterZone(c, V) {
    if (!c.voile) return;
    const m = c.voile.material;
    if (c.local && V.voirLocal) {                 // dégradé par endroit
      c.voile.visible = true;
      m.vertexColors = true;
      m.color.set(0xffffff);
      m.opacity = 0.55;
    } else {                                      // teinte d'ensemble
      c.voile.visible = !!c.couleurZone;
      m.vertexColors = false;
      m.opacity = 0.3;
      if (c.couleurZone) m.color.set(c.couleurZone).convertSRGBToLinear();
    }
    m.needsUpdate = true;
  }

  /** Points de la grille n x n (ligne 0 au nord) dans la zone, par rastérisation de ses contours (pair-impair). */
  function masqueZone(n, L, anneaux) {
    const cv = document.createElement("canvas");
    cv.width = cv.height = n;
    const ctx = cv.getContext("2d");
    ctx.beginPath();
    anneaux.forEach(({ anneau }) => {
      anneau.forEach(([x, y], j) => {
        const u = ((x + L / 2) / L) * (n - 1) + 0.5, v = ((L / 2 - y) / L) * (n - 1) + 0.5;
        if (j) ctx.lineTo(u, v); else ctx.moveTo(u, v);
      });
      ctx.closePath();
    });
    ctx.fillStyle = "#fff";
    ctx.fill("evenodd");
    const px = ctx.getImageData(0, 0, n, n).data;
    const m = new Uint8Array(n * n);
    for (let k = 0; k < n * n; k++) m[k] = px[k * 4 + 3] > 127 ? 1 : 0;
    return m;
  }

  function appliquerSurface(c, surface) {
    const m = c.mesh.material;
    const image = surface === "image" && c.texture;
    m.map = image ? c.texture : null;
    m.vertexColors = !image;
    m.needsUpdate = true;
  }

  /** Altitude (km, exagérée) au point (x, y) du plan, par interpolation bilinéaire de la grille. */
  function hauteurEn(c, x, y, exag) {
    const { n, L, hauteurs } = c;
    const fx = Math.max(0, Math.min(n - 1, ((x + L / 2) / L) * (n - 1)));
    const fy = Math.max(0, Math.min(n - 1, ((L / 2 - y) / L) * (n - 1)));
    const x0 = Math.floor(fx), y0 = Math.floor(fy), x1 = Math.min(n - 1, x0 + 1), y1 = Math.min(n - 1, y0 + 1);
    const ax = fx - x0, ay = fy - y0;
    const h = (r, q) => hauteurs[r * n + q];
    return exag * ((h(y0, x0) * (1 - ax) + h(y0, x1) * ax) * (1 - ay) + (h(y1, x0) * (1 - ax) + h(y1, x1) * ax) * ay);
  }

  function poserHauteurs(c, exag) {
    const T = window.THREE;
    const { n, L, hauteurs } = c;
    const pos = c.mesh.geometry.attributes.position;
    let min = Infinity;
    for (let k = 0; k < n * n; k++) {
      pos.setY(k, hauteurs[k] * exag);
      min = Math.min(min, hauteurs[k] * exag);
    }
    pos.needsUpdate = true;
    c.mesh.geometry.computeVertexNormals();
    c.mesh.geometry.computeBoundingSphere();

    // Socle jusqu'à un peu sous le point le plus bas
    const fond = min - L * 0.04;
    const sommets = [];
    const bord = (ks) => {
      for (let j = 0; j < ks.length - 1; j++) {
        const a = ks[j], b = ks[j + 1];
        const ax = pos.getX(a), ay = pos.getY(a), az = pos.getZ(a), bx = pos.getX(b), by = pos.getY(b), bz = pos.getZ(b);
        sommets.push(ax, ay, az, bx, by, bz, bx, fond, bz, ax, ay, az, bx, fond, bz, ax, fond, az);
      }
    };
    const ligne = (r) => Array.from({ length: n }, (_, q) => r * n + q);
    const colonne = (q) => Array.from({ length: n }, (_, r) => r * n + q);
    bord(ligne(0)); bord(ligne(n - 1)); bord(colonne(0)); bord(colonne(n - 1));
    const g = new T.BufferGeometry();
    g.setAttribute("position", new T.Float32BufferAttribute(sommets, 3));
    g.computeVertexNormals();
    c.socle.geometry.dispose();
    c.socle.geometry = g;

    // Contour de la zone, posé sur le relief
    c.contour.children.slice().forEach((o) => { o.geometry.dispose(); o.material.dispose(); c.contour.remove(o); });
    const materiaux = {};
    c.traits.forEach(({ anneau, couleur = new T.Color(c.couleurZone || "#ffffff").getHex() }) => {
      const mat = materiaux[couleur] || (materiaux[couleur] = new T.LineBasicMaterial({ color: couleur, transparent: true, opacity: 0.9, depthTest: false }));
      const pts = [];
      for (let j = 0; j < anneau.length; j++) {
        const [x0, y0] = anneau[j], [x1, y1] = anneau[(j + 1) % anneau.length];
        const pas = Math.max(1, Math.ceil(Math.hypot(x1 - x0, y1 - y0) / (L / (n - 1))));
        for (let s = 0; s < pas; s++) {
          const x = x0 + ((x1 - x0) * s) / pas, y = y0 + ((y1 - y0) * s) / pas;
          if (Math.abs(x) > L / 2 || Math.abs(y) > L / 2) continue;
          pts.push(new T.Vector3(x, hauteurEn(c, x, y, exag) + L * 0.002, -y));
        }
      }
      if (pts.length > 1) {
        pts.push(pts[0]);
        const l = new T.Line(new T.BufferGeometry().setFromPoints(pts), mat);
        l.renderOrder = 2;
        c.contour.add(l);
      }
    });
  }

  function dimensionner(c) {
    const w = c.conteneur.clientWidth || 1, h = c.conteneur.clientHeight || 1;
    c.renderer.setSize(w, h, false);
    c.camera.aspect = w / h;
    c.camera.updateProjectionMatrix();
  }

  function rendre(V) {
    V.cotes.forEach((c) => c.renderer && c.renderer.render(c.scene, c.camera));
  }

  // ------------------------------------------------------------------ caméras liées
  function lier(V) {
    const T = window.THREE;
    const actifs = V.cotes.filter((c) => c.renderer);
    let copie = false;
    actifs.forEach((c) => {
      const ctl = new T.OrbitControls(c.camera, c.renderer.domElement);
      ctl.target.set(0, 0, 0);
      ctl.enableDamping = false;
      ctl.minDistance = c.L * 0.15;
      ctl.maxDistance = c.L * 4;
      ctl.maxPolarAngle = Math.PI * 0.47;
      ctl.screenSpacePanning = false;
      ctl.update();
      c.ctl = ctl;
      ctl.addEventListener("start", () => {
        if (V.tourne) {
          V.tourne = false;
          V.el.querySelector("#v3-tourner").setAttribute("aria-pressed", "false");
        }
      });
      ctl.addEventListener("change", () => {
        if (copie) return;
        copie = true;
        actifs.forEach((o) => {
          if (o === c) return;
          // Carrés de tailles différentes : même point de vue, rapporté à la taille de chaque carré
          const f = o.L / c.L;
          o.camera.position.copy(c.camera.position).multiplyScalar(f);
          o.camera.quaternion.copy(c.camera.quaternion);
          o.ctl.target.copy(ctl.target).multiplyScalar(f);
          o.ctl.update();
        });
        copie = false;
        rendre(V);
      });
    });
    rendre(V);
    if (V.tourne) animer(V);
  }

  function animer(V) {
    if (V.anime) return;
    V.anime = true;
    let avant = performance.now();
    const pas = (t) => {
      if (!vue || vue !== V || V.arret || !V.tourne || V.mode !== "3d") { V.anime = false; return; }
      const dt = Math.min(100, t - avant);
      avant = t;
      const maitre = V.cotes.find((c) => c.ctl);
      if (maitre) {
        const a = (dt / 1000) * 0.18;                      // ~0,18 rad/s autour de la verticale
        const p = maitre.camera.position.clone().sub(maitre.ctl.target);
        p.applyAxisAngle(new window.THREE.Vector3(0, 1, 0), a);
        maitre.camera.position.copy(maitre.ctl.target).add(p);
        maitre.ctl.update();
      }
      requestAnimationFrame(pas);
    };
    requestAnimationFrame(pas);
  }

  window.vue3D = { ouvrir, fermer, cadreZone };
})();
