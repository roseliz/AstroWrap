// Reference region selection using H3 cells, on both the 3D globe and the 2D map (Mars and Moon).
//
// The region is a set of H3 cells at a fixed base resolution (RES_BASE): exactly the
// cells used during preprocessing. The brush adapts to the zoom level: when zoomed out,
// it paints large cells (subdivided into base-resolution cells); when zoomed in, it paints smaller cells.
//
// Depends on h3-js (window.h3) and window.vueCorps, exposed by globe-mars.js or globe-lune.js.

(function () {
  const v = window.vueCorps;
  const H = window.h3;
  if (!v || !H) {
    console.warn("Area selection unavailable:", !H ? "h3-js could not be loaded." : "vueCorps missing.");
    return;
  }

  // ------------------------------------------------------------------ settings
  const RAYON_H3_KM = 6371.007180918475;     // radius of the sphere on which H3 calculates its surfaces
  const K = v.rayonKm / RAYON_H3_KM;          // length factor Earth -> body
  const RES_BASE = 6;                          // Mars : ~10 km² per tile ; Moon : ~2,7 km²
  const MIN_TUILES = 10;
  const MAX_TUILES = 60000;
  const PINCEAUX = { fin: 0.005, moyen: 0.015, large: 0.04 };   // radius of the brush / width of the view
  const COULEURS = {
    remplissage: "rgba(79, 209, 255, 0.30)",
    trait: "rgba(176, 238, 255, 0.95)",
    pinceau: "rgba(255, 255, 255, 0.95)",
    gomme: "rgba(255, 122, 122, 0.95)",
  };
  const NOM_CORPS = { mars: "Mars", lune: "the Moon" }[v.corps] || v.corps;

  const arete = (res) => H.getHexagonEdgeLengthAvg(res, "km") * K;      // km on the body
  const surfaceTuile = (c) => H.cellArea(c, "km2") * K * K;             // km² on the body
  const distanceKm = (a, b) => H.greatCircleDistance(a, b, "km") * K;
  const surfaceMoyenne = () => H.getHexagonAreaAvg(RES_BASE, "km2") * K * K;
  // A single brush stroke covers at most 1/12 of the maximum area: from a distance, the first gesture remains usable.
  const RAYON_MAX_KM = Math.sqrt((MAX_TUILES * surfaceMoyenne()) / 12 / Math.PI);

  const nb = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  const nb1 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
  const deg = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

  // ------------------------------------------------------------------ state
  const etat = {
    outil: "naviguer",
    pinceau: "moyen",
    tuiles: new Set(),          // cellules H3 à RES_BASE
    historique: [],             // instantanés pour Ctrl+Z
    trait: null,                // trait en cours : { gommer, dernier: [lat, lng] }
    espace: false,              // barre d'espace maintenue : navigation temporaire
    survol: null,               // [lat, lng] sous le curseur
    message: null,
  };

  // ------------------------------------------------------------------ panneau
  const panneau = document.createElement("details");
  panneau.className = "zone";
  panneau.open = !window.matchMedia("(max-width: 720px)").matches;
  panneau.innerHTML = `
    <summary><span class="zone-titre">Reference area</span><span class="zone-resume" id="zone-resume"></span></summary>
    <div class="zone-corps">
      <div class="zone-outils" role="group" aria-label="Tool">
        <button type="button" data-outil="naviguer" title="Navigate (V)">Navigate</button>
        <button type="button" data-outil="peindre" title="Paint tiles (B)">Paint</button>
        <button type="button" data-outil="gommer" title="Erase tiles (E)">Erase</button>
      </div>
      <div class="zone-ligne">
        <span>Brush</span>
        <div class="zone-tailles" role="group" aria-label="Brush size">
          <button type="button" data-pinceau="fin" title="Fine brush ([)">Fine</button>
          <button type="button" data-pinceau="moyen" title="Medium brush">Medium</button>
          <button type="button" data-pinceau="large" title="Large brush (])">Large</button>
        </div>
      </div>
      <dl class="zone-stats">
        <dt>Area</dt><dd id="zone-surface">–</dd>
        <dt>Tiles</dt><dd id="zone-tuiles">–</dd>
        <dt>Parts</dt><dd id="zone-parties">–</dd>
        <dt>Center</dt><dd id="zone-centre">–</dd>
      </dl>
      <p class="zone-message" id="zone-message" role="status" aria-live="polite"></p>
      <div class="zone-actions">
        <button type="button" id="zone-annuler" title="Undo (Ctrl+Z)">Undo</button>
        <button type="button" id="zone-effacer">Clear all</button>
        <button type="button" id="zone-exporter" title="Download the area (JSON)">Export</button>
      </div>
      <button type="button" id="zone-comparer" class="zone-comparer" title="Search the Earth for places that look like this area">Compare with Earth</button>
      <p class="zone-astuce">B paint · E erase · V navigate · Shift erases while painting · hold Space to move the view · [ ] size · Ctrl+Z undo</p>
    </div>`;
  document.body.appendChild(panneau);
  const $ = (s) => panneau.querySelector(s);

  panneau.querySelectorAll("[data-outil]").forEach((b) => b.addEventListener("click", () => choisirOutil(b.dataset.outil)));
  panneau.querySelectorAll("[data-pinceau]").forEach((b) => b.addEventListener("click", () => choisirPinceau(b.dataset.pinceau)));
  $("#zone-annuler").addEventListener("click", annuler);
  $("#zone-effacer").addEventListener("click", () => {
    if (!etat.tuiles.size) return;
    memoriser();
    etat.tuiles.clear();
    apresChangement(true);
  });
  $("#zone-exporter").addEventListener("click", exporter);
  $("#zone-comparer").addEventListener("click", comparerAvecTerre);

  // ------------------------------------------------------------------ outils
  function navigationActive() {
    return etat.outil === "naviguer" || etat.espace;
  }

/** Enables or disables view dragging depending on the selected tool (mouse wheel zoom remains enabled at all times). */
  function appliquerModeVue() {
    const nav = navigationActive();
    document.body.dataset.outil = nav ? "naviguer" : etat.outil;
    if (v.globe) v.globe.controls().enableRotate = nav;
    const p = v.plane();
    if (p) {
      if (nav) p.carte.dragging.enable(); else p.carte.dragging.disable();
      p.carte.boxZoom.disable();   // Maj + glisser sert à gommer
    }
    if (nav) cacherPinceau();
  }

  function choisirOutil(o) {
    etat.outil = o;
    panneau.querySelectorAll("[data-outil]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.outil === o)));
    if (o !== "naviguer") v.arreterRotation();
    appliquerModeVue();
    majMessage();
  }

  function choisirPinceau(t) {
    etat.pinceau = t;
    panneau.querySelectorAll("[data-pinceau]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.pinceau === t)));
    if (etat.survol) montrerPinceau(etat.survol, etat.trait ? etat.trait.gommer : etat.outil === "gommer");
  }

  // ------------------------------------------------------------------ pinceau
  /** Cells covered by the brush around a point. Their resolution follows the zoom. */
  function empreinte(lat, lng) {
    const rayon = rayonPinceau();
    let res = RES_BASE;
    // On remonte vers des cellules plus grandes tant que le pinceau en couvrirait trop.
    while (res > RES_BASE - 3 && rayon / (arete(res) * Math.sqrt(3)) > 10) res--;
    const centre = H.latLngToCell(lat, lng, res);
    const anneaux = Math.min(12, Math.round(rayon / (arete(res) * Math.sqrt(3))));
    const cellules = H.gridDisk(centre, anneaux).filter((c) => c === centre || distanceKm([lat, lng], H.cellToLatLng(c)) <= rayon);
    return { cellules, res };
  }

  /** Applies the brush between the previous point and the current point (without gaps if the mouse moves quickly). */
  function peindreJusqua(lat, lng) {
    const t = etat.trait;
    const points = [];
    if (t.dernier) {
      const [la0, ln0] = t.dernier;
      let dln = lng - ln0;
      if (dln > 180) dln -= 360;
      if (dln < -180) dln += 360;
      const rayon = Math.max(arete(RES_BASE), rayonPinceau());
      const n = Math.min(40, Math.ceil(distanceKm(t.dernier, [lat, lng]) / (rayon * 0.6)));
      for (let i = 1; i <= n; i++) points.push([la0 + ((lat - la0) * i) / n, ln0 + (dln * i) / n]);
    } else {
      points.push([lat, lng]);
    }
    t.dernier = [lat, lng];

    const touchees = new Set();
    for (const [la, ln] of points) {
      const { cellules, res } = empreinte(la, ((ln + 540) % 360) - 180);
      const fines = res === RES_BASE ? cellules : H.uncompactCells(cellules, RES_BASE);
      fines.forEach((c) => touchees.add(c));
    }

    if (t.gommer) {
      let change = false;
      touchees.forEach((c) => { if (etat.tuiles.delete(c)) change = true; });
      if (change) apresChangement();
      return;
    }
    const nouvelles = [...touchees].filter((c) => !etat.tuiles.has(c));
    if (!nouvelles.length) return;
    if (etat.tuiles.size + nouvelles.length > MAX_TUILES) {
      etat.message = { type: "alerte", texte: `Area too large: at most ${nb.format(MAX_TUILES)} tiles (~${nb.format(MAX_TUILES * surfaceMoyenne())} km²). Zoom in or use a finer brush.` };
      majMessage();
      return;
    }
    nouvelles.forEach((c) => etat.tuiles.add(c));
    apresChangement();
  }

  function rayonPinceau() {
    return Math.min(RAYON_MAX_KM, v.largeurVueKm() * PINCEAUX[etat.pinceau]);
  }

  // ------------------------------------------------------------------ souris et doigts
  /** Coordinates under the pointer, in the active view ; null outside the planet. */
  function coordsPointeur(e) {
    if (v.mode() === "carte") {
      const p = v.plane();
      if (!p) return null;
      const ll = p.carte.mouseEventToLatLng(e);
      if (Math.abs(ll.lat) > 90 || Math.abs(ll.lng) > 180) return null;
      return [ll.lat, ll.lng];
    }
    const r = v.conteneur.getBoundingClientRect();
    const c = v.coordsSousPoint(e.clientX - r.left, e.clientY - r.top);
    return c ? [c.lat, c.lng] : null;
  }

  function debutTrait(e) {
    if (navigationActive() || e.button !== 0) return;
    const c = coordsPointeur(e);
    if (!c) return;
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.setPointerCapture?.(e.pointerId);
    memoriser();
    etat.message = null;
    etat.trait = { gommer: etat.outil === "gommer" || e.shiftKey, dernier: null, change: false };
    peindreJusqua(c[0], c[1]);
    montrerPinceau(c, etat.trait.gommer);
  }

  function mouvement(e) {
    if (navigationActive()) return;
    const c = coordsPointeur(e);
    etat.survol = c;
    if (!c) { cacherPinceau(); return; }
    const gommer = etat.trait ? etat.trait.gommer : etat.outil === "gommer" || e.shiftKey;
    if (etat.trait) peindreJusqua(c[0], c[1]);
    montrerPinceau(c, gommer);
  }

  function finTrait() {
    if (!etat.trait) return;
    etat.trait = null;
    // A stroke that hasn't changed anything shouldn't clutter the history.
    const avant = etat.historique[etat.historique.length - 1];
    if (avant && avant.length === etat.tuiles.size && avant.every((c) => etat.tuiles.has(c))) etat.historique.pop();
    apresChangement(true);
  }

  function brancher(element) {
    if (!element || element.dataset.zoneBranche) return;
    element.dataset.zoneBranche = "1";
    // Capture phase: runs before the camera or Leaflet controls.
    element.addEventListener("pointerdown", debutTrait, true);
    element.addEventListener("pointermove", mouvement);
    element.addEventListener("pointerup", finTrait);
    element.addEventListener("pointercancel", finTrait);
    element.addEventListener("pointerleave", () => { etat.survol = null; if (!etat.trait) cacherPinceau(); });
  }

  // ------------------------------------------------------------------ Keyboard
  window.addEventListener("keydown", (e) => {
    if (e.target.closest && e.target.closest("input, textarea, select")) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); annuler(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === " " && !etat.espace && etat.outil !== "naviguer") {
      e.preventDefault();
      etat.espace = true;
      appliquerModeVue();
      return;
    }
    const k = e.key.toLowerCase();
    if (k === "b") choisirOutil("peindre");
    else if (k === "e") choisirOutil("gommer");
    else if (k === "v") choisirOutil("naviguer");
    else if (e.key === "[") choisirPinceau(etat.pinceau === "large" ? "moyen" : "fin");
    else if (e.key === "]") choisirPinceau(etat.pinceau === "fin" ? "moyen" : "large");
  });
  window.addEventListener("keyup", (e) => {
    if (e.key === " " && etat.espace) {
      etat.espace = false;
      appliquerModeVue();
    }
  });

  // ------------------------------------------------------------------ history
  function memoriser() {
    etat.historique.push([...etat.tuiles]);
    if (etat.historique.length > 30) etat.historique.shift();
  }
  function annuler() {
    const precedent = etat.historique.pop();
    if (!precedent) return;
    etat.tuiles = new Set(precedent);
    etat.message = null;
    apresChangement(true);
  }

  // ------------------------------------------------------------------ drawing
  let cacheCompactes = [];
  let compactesAJour = true;
  let renduPrevu = false;

  /** The zone in compact form (large cells where the zone is full). */
  function compactes() {
    if (!compactesAJour) {
      cacheCompactes = etat.tuiles.size ? H.compactCells([...etat.tuiles]) : [];
      compactesAJour = true;
    }
    return cacheCompactes;
  }

  function apresChangement(complet = false) {
    compactesAJour = false;
    if (!renduPrevu) {
      renduPrevu = true;
      requestAnimationFrame(() => {
        renduPrevu = false;
        dessiner3D();
        dessiner2D();
        majStatsRapides();
      });
    }
    if (complet) planifierStatsCompletes();
  }

  // --- 3D
// globe.gl polygons recalculate geometry for each cell (taking more than a second for just a few
// dozen cells): instead, we build a single mesh (triangle fans) and a single set of
// line segments for all cells, positioned just above the surface.
  const RES_DESSIN_MIN = 3;          
  const ALT_TUILES = 0.0015;        
  const ALT_PINCEAU = 0.003;
  let objets3D = null;

/** three.js classes retrieved from the globe objects (globe.gl does not export three.js). */
  function preparer3D() {
    if (objets3D || !v.globe) return Boolean(objets3D);
    const scene = v.globe.scene();
    let traits = null, maillage = null;
    scene.traverse((o) => {
      if (!traits && o.isLineSegments) traits = o;
      if (!maillage && o.isMesh && o.geometry && o.geometry.index) maillage = o;
    });
    if (!traits || !maillage) return false;
    const T = {
      LineSegments: traits.constructor,
      Materiau: traits.material.constructor,               // LineBasicMaterial 
      Mesh: maillage.constructor,
      Geometrie: maillage.geometry.toNonIndexed().constructor,  // BufferGeometry 
      Attribut: maillage.geometry.attributes.position.constructor,
    };
    const materiau = (couleur, opacite) => new T.Materiau({ color: couleur, transparent: true, opacity: opacite, depthWrite: false });
    objets3D = {
      T,
      remplissage: new T.Mesh(new T.Geometrie(), materiau("#4FD1FF", 0.3)),
      contours: new T.LineSegments(new T.Geometrie(), materiau("#B0EEFF", 0.95)),
      pinceau: new T.LineSegments(new T.Geometrie(), materiau("#FFFFFF", 0.95)),
    };
    for (const [i, o] of [objets3D.remplissage, objets3D.contours, objets3D.pinceau].entries()) {
      o.renderOrder = 2 + i;
      o.frustumCulled = false;
      scene.add(o);
    }
    return true;
  }

  const point3D = (lat, lng, alt) => { const p = v.globe.getCoords(lat, lng, alt); return [p.x, p.y, p.z]; };

  function remplacerGeometrie(objet, positions) {
    const { T } = objets3D;
    const g = new T.Geometrie();
    g.setAttribute("position", new T.Attribut(new Float32Array(positions), 3));
    objet.geometry.dispose();
    objet.geometry = g;
  }

  function dessiner3D() {
    if (!preparer3D()) return;
    const cellules = [];
    for (const c of compactes()) {
      if (H.getResolution(c) >= RES_DESSIN_MIN) cellules.push(c);
      else cellules.push(...H.cellToChildren(c, RES_DESSIN_MIN));
    }
    const tri = [], seg = [];
    for (const c of cellules) {
      const bord = H.cellToBoundary(c).map(([la, ln]) => point3D(la, ln, ALT_TUILES));
      const centre = point3D(...H.cellToLatLng(c), ALT_TUILES);
      for (let i = 0; i < bord.length; i++) {
        const a = bord[i], b = bord[(i + 1) % bord.length];
        tri.push(...centre, ...a, ...b);
        seg.push(...a, ...b);
      }
    }
    remplacerGeometrie(objets3D.remplissage, tri);
    remplacerGeometrie(objets3D.contours, seg);
  }

  // --- 2D (Leaflet, rendu sur canvas)
  let couche2D = null;
  let pinceau2D = null;
  let rendu2D = null;

  function preparer2D() {
    const p = v.plane();
    if (!p || couche2D) return Boolean(couche2D);
    rendu2D = L.canvas({ padding: 0.3 });
    couche2D = L.layerGroup().addTo(p.carte);
    pinceau2D = L.layerGroup().addTo(p.carte);
    brancher(p.element);
    appliquerModeVue();
    return true;
  }

  /** Contour(s) d'une cellule en coordonnées 2D : gère la ligne de changement de date et les pôles. */
  function contours2D(boucle, cellule) {
    const lngs = boucle.map((p) => p[1]);
    if (Math.max(...lngs) - Math.min(...lngs) <= 180) return [boucle];
    // Cellule qui contient un pôle : on la ferme le long du bord haut ou bas de la carte.
    const pole = cellule && [90, -90].find((la) => H.latLngToCell(la, 0, H.getResolution(cellule)) === cellule);
    if (pole !== undefined) {
      const tries = boucle.slice().sort((a, b) => a[1] - b[1]);
      return [[[pole, -180], ...tries, [pole, 180]]];
    }
    // Cellule à cheval sur ±180° : deux copies décalées, chacune coupée par le bord de la carte.
    const est = boucle.map(([la, ln]) => [la, ln < 0 ? ln + 360 : ln]);
    return [est, est.map(([la, ln]) => [la, ln - 360])];
  }

  function dessiner2D() {
    if (!preparer2D()) return;
    couche2D.clearLayers();
    const style = { renderer: rendu2D, color: COULEURS.trait, weight: 1, fillColor: "#4FD1FF", fillOpacity: 0.3, interactive: false };
    for (const c of compactes()) {
      for (const contour of contours2D(H.cellToBoundary(c), c)) L.polygon(contour, style).addTo(couche2D);
    }
  }

  // --- aperçu du pinceau (contour pointillé sous le curseur)
  function montrerPinceau(c, gommer) {
    if (navigationActive() || !c) return;
    const { cellules } = empreinte(c[0], c[1]);
    const boucles = H.cellsToMultiPolygon(cellules, false).map((poly) => poly[0]);
    const couleur = gommer ? COULEURS.gomme : COULEURS.pinceau;
    if (v.mode() === "carte") {
      if (!preparer2D()) return;
      pinceau2D.clearLayers();
      for (const b of boucles) {
        for (const contour of contours2D(b)) {
          L.polygon(contour, { renderer: rendu2D, color: couleur, weight: 2, dashArray: "4 4", fill: false, interactive: false }).addTo(pinceau2D);
        }
      }
    } else if (preparer3D()) {
      const seg = [];
      for (const b of boucles) {
        const pts = b.map(([la, ln]) => point3D(la, ln, ALT_PINCEAU));
        for (let i = 0; i < pts.length; i++) seg.push(...pts[i], ...pts[(i + 1) % pts.length]);
      }
      objets3D.pinceau.material.color.set(gommer ? "#FF7A7A" : "#FFFFFF");
      remplacerGeometrie(objets3D.pinceau, seg);
      objets3D.pinceau.visible = true;
    }
  }

  function cacherPinceau() {
    if (objets3D) objets3D.pinceau.visible = false;
    if (pinceau2D) pinceau2D.clearLayers();
  }

  // ------------------------------------------------------------------ chiffres de la zone
  function surfaceKm2() {
    return compactes().reduce((s, c) => s + surfaceTuile(c), 0);
  }

  /** Centre de la zone : moyenne des positions sur la sphère, pondérée par la surface. */
  function centre() {
    let x = 0, y = 0, z = 0;
    for (const c of compactes()) {
      const [la, ln] = H.cellToLatLng(c).map((d) => (d * Math.PI) / 180);
      const w = surfaceTuile(c);
      x += w * Math.cos(la) * Math.cos(ln);
      y += w * Math.cos(la) * Math.sin(ln);
      z += w * Math.sin(la);
    }
    return [Math.atan2(z, Math.hypot(x, y)) * (180 / Math.PI), Math.atan2(y, x) * (180 / Math.PI)];
  }

  /** Nombre de morceaux séparés (tuiles voisines = même morceau). */
  function compterParties() {
    const restantes = new Set(etat.tuiles);
    let parties = 0;
    while (restantes.size) {
      parties++;
      const depart = restantes.values().next().value;
      restantes.delete(depart);
      const pile = [depart];
      while (pile.length) {
        for (const voisine of H.gridDisk(pile.pop(), 1)) {
          if (restantes.delete(voisine)) pile.push(voisine);
        }
      }
    }
    return parties;
  }

  const lireCoords = ([la, ln]) => `${deg.format(Math.abs(la))}° ${la >= 0 ? "N" : "S"}, ${deg.format(Math.abs(ln))}° ${ln >= 0 ? "E" : "W"}`;
  const formatSurface = (s) => (s >= 100 ? nb.format(s) : nb1.format(s)) + " km²";

  function majStatsRapides() {
    const n = etat.tuiles.size;
    $("#zone-tuiles").textContent = n ? `${nb.format(n)} (~${nb1.format(surfaceMoyenne())} km² each)` : "–";
    $("#zone-surface").textContent = n ? formatSurface(surfaceKm2()) : "–";
    $("#zone-resume").textContent = n ? formatSurface(surfaceKm2()) : "";
    if (!n) { $("#zone-centre").textContent = "–"; $("#zone-parties").textContent = "–"; }
    majMessage();
  }

  let minuterieStats = null;
  let parties = 0;
  function planifierStatsCompletes() {
    clearTimeout(minuterieStats);
    minuterieStats = setTimeout(() => {
      const n = etat.tuiles.size;
      parties = n ? compterParties() : 0;
      $("#zone-parties").textContent = n ? nb.format(parties) : "–";
      $("#zone-centre").textContent = n ? lireCoords(centre()) : "–";
      majMessage();
      majAdresse();
      // the satellites (js/satellites.js) come and stand above the area
      document.dispatchEvent(new CustomEvent("zone:changee", { detail: { tuiles: n, centre: n ? centre() : null, surfaceKm2: n ? surfaceKm2() : 0 } }));
    }, 150);
  }

  function majMessage() {
    const n = etat.tuiles.size;
    let m = etat.message;
    if (!m) {
      if (!n) {
        m = etat.outil === "naviguer"
          ? { type: "info", texte: `Choose “Paint”, then drag over ${NOM_CORPS}: the painted tiles form the area compared with Earth.` }
          : { type: "info", texte: "Drag to paint. Seen from afar, the brush lays large tiles; zoom in to be precise." };
      } else if (n < MIN_TUILES) {
        m = { type: "alerte", texte: `Area too small: at least ${MIN_TUILES} tiles (~${nb.format(MIN_TUILES * surfaceMoyenne())} km²) for the data to be representative.` };
      } else if (parties > 1) {
        m = { type: "info", texte: `${parties} separate parts: they will form a single reference.` };
      }
    }
    const el = $("#zone-message");
    el.textContent = m ? m.texte : "";
    el.dataset.type = m ? m.type : "";
  }

  // ------------------------------------------------------------------ adresse de la page et export
  /** La zone est gardée dans le navigateur (localStorage), jamais dans l'adresse : un rechargement la retrouve,
   *  et la page du globe terrestre la lit au clic sur « Comparer avec la Terre ». */
  const CLE_ZONE = `analogues-zone-${{ lune: "moon" }[v.corps] || v.corps}`;
  // Serveur : local (http://127.0.0.1:8000) sur cette machine ou en file://, https://api.astrowrap.earth en ligne ; ?api=... l'emporte.
  const API = (new URLSearchParams(location.search).get("api") || (/^(localhost|127\.0\.0\.1|\[::1\]|)$/.test(location.hostname) ? "http://127.0.0.1:8000" : "https://api.astrowrap.earth")).replace(/\/$/, "");
  function majAdresse() {
    const liste = compactes();
    try {
      if (liste.length) localStorage.setItem(CLE_ZONE, liste.join(","));
      else localStorage.removeItem(CLE_ZONE);
    } catch (e) { /* navigation privée ou stockage plein : la zone reste seulement dans la page */ }
  }

  /** Retour depuis la Terre (mars.html#<id>) : la zone comparée, relue sur le serveur. */
  function lireZoneServeur() {
    const m = location.hash.match(/^#([0-9a-f]{12})$/);
    if (!m) return;
    history.replaceState(null, "", location.pathname + location.search);
    fetch(`${API}/api/zones/${m[1]}`).then((r) => (r.ok ? r.json() : null)).then((d) => {
      if (!d || !d.h3_cells) return;
      const tuiles = new Set();
      H.uncompactCells(d.h3_cells.filter((c) => H.isValidCell(c) && H.getResolution(c) <= RES_BASE), RES_BASE)
        .forEach((c) => tuiles.add(c));
      if (!tuiles.size) return;
      etat.tuiles.clear();
      tuiles.forEach((c) => etat.tuiles.add(c));
      apresChangement(true);
    }).catch(() => {});
  }

  function lireAdresse() {
    // Anciennes adresses (#zone=...) : lues une fois, puis retirées de la barre d'adresse.
    const m = location.hash.match(/zone=([0-9a-f,]+)/i);
    if (m) history.replaceState(null, "", location.pathname + location.search);
    let texte = m ? m[1] : "";
    if (!texte) {
      try { texte = localStorage.getItem(CLE_ZONE) || ""; } catch (e) { texte = ""; }
    }
    const cellules = texte.split(",").filter((c) => H.isValidCell(c) && H.getResolution(c) <= RES_BASE);
    if (!cellules.length) return;
    try {
      H.uncompactCells(cellules, RES_BASE).forEach((c) => etat.tuiles.add(c));
    } catch (e) {
      console.warn("Saved area unreadable:", e.message);
    }
  }

  function exporter() {
    if (!etat.tuiles.size) {
      etat.message = { type: "alerte", texte: "Nothing to export: paint an area first." };
      majMessage();
      etat.message = null;
      return;
    }
    const [lat, lng] = centre();
    const donnees = {
      corps: v.corps,
      rayon_km: v.rayonKm,
      resolution_h3: RES_BASE,
      nombre_tuiles: etat.tuiles.size,
      surface_km2: Math.round(surfaceKm2()),
      parties,
      centre: { lat: +lat.toFixed(4), lng: +lng.toFixed(4) },
      cellules_compactees: compactes(),
      cree_le: new Date().toISOString(),
      note: "H3 cells in planetocentric latitude/longitude of the body. For the full list: h3.uncompact_cells(cellules_compactees, resolution_h3).",
    };
    const lien = document.createElement("a");
    lien.href = URL.createObjectURL(new Blob([JSON.stringify(donnees, null, 2)], { type: "application/json" }));
    lien.download = `zone-${v.corps}-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(lien);
    lien.click();
    lien.remove();
    setTimeout(() => URL.revokeObjectURL(lien.href), 2000);
  }

  /** Envoie la zone au serveur (POST /api/zones) et ouvre index.html#mars/<id> : l'adresse ne porte qu'un
   *  identifiant court. Sans serveur, la zone passe par localStorage (même navigateur, même origine). */
  async function comparerAvecTerre() {
    if (etat.tuiles.size < MIN_TUILES) {
      etat.message = { type: "alerte", texte: `First paint an area of at least ${MIN_TUILES} tiles.` };
      majMessage();
      etat.message = null;
      return;
    }
    const corps = { lune: "moon" }[v.corps] || v.corps;
    const api = new URLSearchParams(location.search).get("api");
    const page = `index.html${api ? "?api=" + encodeURIComponent(api) : ""}`;
    const zone = compactes();
    const bouton = $("#zone-comparer");
    bouton.disabled = true;
    bouton.textContent = "Sending the area…";
    let stockee = true;
    try { localStorage.setItem(CLE_ZONE, zone.join(",")); } catch (e) { stockee = false; }
    try {
      const r = await fetch(`${API}/api/zones`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: corps, h3_cells: zone }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) {
        etat.message = { type: "alerte", texte: `The server rejects the area: ${d.detail || r.status}` };
        majMessage();
        etat.message = null;
        bouton.disabled = false;
        bouton.textContent = "Compare with Earth";
        return;
      }
      location.href = `${page}#${corps}/${d.id}`;
    } catch (e) {
      // Serveur injoignable : la page de la Terre le dira ; la zone y arrive par le navigateur, sinon par l'adresse.
      location.href = stockee ? `${page}#${corps}` : `${page}#corps=${corps}&zone=${zone.join(",")}`;
    }
  }

  // ------------------------------------------------------------------ démarrage
  brancher(v.conteneur);
  document.addEventListener("vue:changee", () => {
    cacherPinceau();
    preparer2D();
    appliquerModeVue();
    dessiner2D();
  });
  choisirOutil("naviguer");
  choisirPinceau("moyen");
  lireAdresse();
  apresChangement(true);
  lireZoneServeur();

  window.selectionZone = {
    tuiles: () => [...etat.tuiles],
    centre: () => (etat.tuiles.size ? centre() : null),
    surfaceKm2: () => (etat.tuiles.size ? surfaceKm2() : 0),
    compactes: () => compactes().slice(),
    resolution: RES_BASE,
    triangles3D: () => (objets3D && objets3D.remplissage.geometry.attributes.position ? objets3D.remplissage.geometry.attributes.position.count / 3 : 0),
  };
})();
