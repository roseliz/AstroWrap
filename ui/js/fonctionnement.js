// How it works (fonctionnement.html): two animated panels, drawn on a canvas, no library except h3-js.
//
//   1. Pre-processing (offline): satellite maps -> H3 hexagons -> each hexagon reads its pixels -> one row per cell
//      in small Parquet tables (DuckDB).
//   2. The search (live): the painted area goes to the server -> its fingerprint -> the Earth cells cross every
//      module, those that keep looking less alike are dropped -> the top sites come back.
//
// Each panel has 4 steps: they play one after another while the panel is on screen, a step button jumps to it,
// ❚❚ pauses, ↺ replays. The hexagons are real H3 cells (drawn at resolution 1: the real ones, resolution 5, are
// 2,400 times smaller). The map colors are generated (illustration), the funnel numbers come from an example search.

(function () {
  const H = window.h3;
  const reduit = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const RAD = Math.PI / 180;
  const nb = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  const POLICE = '"Archivo", "Helvetica Neue", Arial, sans-serif';
  const TEXTE = "#E9EEF5", DOUX = "#9DAAC0", TRAIT = "rgba(169, 200, 238, 0.22)", CIEL = "#A9C8EE";
  // mêmes couleurs que les satellites (js/satellites.js)
  const MODULES = [
    { cle: "topography", nom: "Terrain", court: "Terrain", c: "#F2C14E" },
    { cle: "thermal", nom: "Temperature", court: "Temp.", c: "#F2545B" },
    { cle: "geology", nom: "Rocks", court: "Rocks", c: "#E07A5F" },
    { cle: "wind", nom: "Wind and dust", court: "Wind", c: "#C9A0DC" },
    { cle: "volatiles", nom: "Ice and water", court: "Ice", c: "#7CC6FE" },
    { cle: "astro", nom: "Volcanoes and caves", court: "Caves", c: "#3DDC97" },
  ];

  const borne = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  const sortie = (x) => 1 - (1 - borne(x)) ** 3;                    // ease-out
  const douce = (x) => { x = borne(x); return x * x * (3 - 2 * x); };
  const melange = (a, b, m) => a + (b - a) * m;
  const fenetre = (k, a, b) => borne((k - a) / (b - a));             // progress of k inside [a, b]

  // ------------------------------------------------------------------ globe: projection and generated maps
  /** Orthographic projection centered on (lat0, lon0): [x, y, z] on the unit sphere, z > 0 = visible side. */
  function projection(lat0, lon0) {
    const c0 = Math.cos(lat0 * RAD), s0 = Math.sin(lat0 * RAD);
    return (lat, lon) => {
      const la = lat * RAD, dl = (lon - lon0) * RAD, cl = Math.cos(la);
      return [cl * Math.sin(dl), -(c0 * Math.sin(la) - s0 * cl * Math.cos(dl)), s0 * Math.sin(la) + c0 * cl * Math.cos(dl)];
    };
  }
  const hache = (a, b) => { const s = Math.sin(a * 127.1 + b * 311.7) * 43758.5453; return s - Math.floor(s); };
  function bruit(x, y) {
    const xi = Math.floor(x), yi = Math.floor(y), u = douce(x - xi), v = douce(y - yi);
    const a = hache(xi, yi), b = hache(xi + 1, yi), c = hache(xi, yi + 1), d = hache(xi + 1, yi + 1);
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
  }
  /** A smooth field on the sphere (no seam at 180°): noise of the 3D position. */
  function champ(lat, lon, echelle = 2.2, graine = 0) {
    const cl = Math.cos(lat * RAD), x = cl * Math.cos(lon * RAD), y = cl * Math.sin(lon * RAD), z = Math.sin(lat * RAD);
    const X = echelle * (x + 0.6 * z) + 7 + graine, Y = echelle * (y - 0.4 * z) + 3 - graine;
    return 0.55 * bruit(X, Y) + 0.3 * bruit(2 * X + 5, 2 * Y) + 0.15 * bruit(4 * X, 4 * Y + 9);
  }
  function degrade(stops, t) {
    t = borne(t) * (stops.length - 1);
    const i = Math.min(stops.length - 2, Math.floor(t)), f = t - i, a = stops[i], b = stops[i + 1];
    return [0, 1, 2].map((j) => Math.round(a[j] + (b[j] - a[j]) * f));
  }
  const hex = (s) => [1, 3, 5].map((i) => parseInt(s.slice(i, i + 2), 16));
  const PALETTES = {
    earth: ["#173A6B", "#1F6F8B", "#5FAF7A", "#D9C25A", "#E0794F"].map(hex),
    mars: ["#4A1E14", "#8A3B22", "#C2643A", "#E39A62", "#F2C9A0"].map(hex),
  };
  /** A raster of "pixels" every `pas` degrees, with a value and a color: what a satellite map looks like. */
  function raster(pas, palette, graine) {
    const px = [];
    for (let lat = -90 + pas / 2; lat < 90; lat += pas) {
      for (let lon = -180 + pas / 2; lon < 180; lon += pas) {
        const v = borne(0.75 * champ(lat, lon, 2.2, graine) + 0.35 * Math.cos(lat * RAD) - 0.1);
        const [r, g, b] = degrade(palette, v);
        px.push({ lat, lon, v, coul: `rgb(${r},${g},${b})`, ordre: hache(lat * 3.1, lon * 1.7) });
      }
    }
    return px;
  }
  /** Real colors, once an image is loaded: an equirectangular texture (Mars) or Web Mercator tiles (Earth, Esri
   *  World Imagery at zoom 1, the same imagery as the Earth globe). Returns a promise of a sampler (lat, lon) -> "rgb()",
   *  or null if the image cannot be read (the generated colors then stay). */
  function echantillonneur(sources, mercator) {
    const cote = Math.round(Math.sqrt(sources.length));
    return Promise.all(sources.map((src) => new Promise((ok) => {
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => ok(img); img.onerror = () => ok(null);
      img.src = src;
    }))).then((imgs) => {
      if (imgs.some((i) => !i)) return null;
      const t = mercator ? 256 : imgs[0].naturalWidth, h = mercator ? 256 : imgs[0].naturalHeight;
      const W = mercator ? t * cote : Math.min(1024, t), Hh = mercator ? t * cote : Math.round(W * h / t);
      const c = document.createElement("canvas"); c.width = W; c.height = Hh;
      const g = c.getContext("2d");
      if (mercator) imgs.forEach((im, k) => g.drawImage(im, (k % cote) * t, Math.floor(k / cote) * t, t, t));
      else g.drawImage(imgs[0], 0, 0, W, Hh);
      let d;
      try { d = g.getImageData(0, 0, W, Hh).data; } catch (e) { return null; }
      return (lat, lon) => {
        const x = Math.min(W - 1, Math.max(0, Math.floor(((lon + 180) / 360) * W)));
        let y;
        if (mercator) {
          const la = Math.max(-85, Math.min(85, lat)) * RAD;
          y = Math.floor(((1 - Math.log(Math.tan(Math.PI / 4 + la / 2)) / Math.PI) / 2) * Hh);
        } else y = Math.floor(((90 - lat) / 180) * Hh);
        const i = (Math.min(Hh - 1, Math.max(0, y)) * W + x) * 4;
        return `rgb(${d[i]},${d[i + 1]},${d[i + 2]})`;
      };
    });
  }
  const TUILES_TERRE = [0, 1].flatMap((y) => [0, 1].map((x) =>
    `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/1/${y}/${x}`));
  const recolorer = (px, f) => { if (f) px.forEach((p) => (p.coul = f(p.lat, p.lon))); return f; };

  /** Draws a globe (raster + rim) and returns its projector to screen. */
  function globe(ctx, G, px, pas, alpha = 1, filtre) {
    const P = projection(G.lat0, G.lon0);
    ctx.save();
    ctx.beginPath(); ctx.arc(G.x, G.y, G.R, 0, 2 * Math.PI); ctx.fillStyle = "#0A1426"; ctx.fill();
    ctx.clip();
    const taille = Math.max(1.2, G.R * pas * RAD * 1.08);
    for (const p of px) {
      const [x, y, z] = P(p.lat, p.lon);
      if (z <= 0.02) continue;
      const a = filtre ? filtre(p) : 1;
      if (a <= 0.01) continue;
      ctx.globalAlpha = alpha * a * (0.45 + 0.55 * z);
      ctx.fillStyle = p.coul;
      ctx.fillRect(G.x + G.R * x - taille / 2, G.y + G.R * y - taille / 2, taille, taille);
    }
    ctx.restore();
    // limbe : ombre sur le bord, halo
    const ombre = ctx.createRadialGradient(G.x - G.R * 0.3, G.y - G.R * 0.35, G.R * 0.2, G.x, G.y, G.R);
    ombre.addColorStop(0, "rgba(255,255,255,0.06)"); ombre.addColorStop(0.75, "rgba(0,0,0,0)"); ombre.addColorStop(1, "rgba(0,0,0,0.5)");
    ctx.globalAlpha = alpha;
    ctx.beginPath(); ctx.arc(G.x, G.y, G.R, 0, 2 * Math.PI); ctx.fillStyle = ombre; ctx.fill();
    ctx.strokeStyle = "rgba(169, 200, 238, 0.35)"; ctx.lineWidth = 1; ctx.stroke();
    ctx.globalAlpha = 1;
    return (lat, lon) => { const [x, y, z] = P(lat, lon); return { x: G.x + G.R * x, y: G.y + G.R * y, z }; };
  }
  /** Outlines (and optional fill) of H3 cells on a globe; `style(i)` returns { alpha, fill } or null. */
  function cellules(ctx, ecran, bords, style) {
    bords.forEach((b, i) => {
      const s = style(i);
      if (!s || s.alpha <= 0.01) return;
      const pts = b.map(([la, lo]) => ecran(la, lo));
      if (pts.some((p) => p.z <= 0.05)) return;
      ctx.beginPath();
      pts.forEach((p, j) => (j ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
      ctx.closePath();
      if (s.fill) { ctx.globalAlpha = s.alpha * (s.fillAlpha ?? 0.6); ctx.fillStyle = s.fill; ctx.fill(); }
      ctx.globalAlpha = s.alpha; ctx.strokeStyle = s.trait || "rgba(233, 238, 245, 0.75)"; ctx.lineWidth = s.epaisseur || 0.8; ctx.stroke();
    });
    ctx.globalAlpha = 1;
  }

  // ------------------------------------------------------------------ small drawing helpers
  function texte(ctx, t, x, y, { taille = 13, poids = 700, coul = TEXTE, align = "left", base = "alphabetic", alpha = 1, espace = 0 } = {}) {
    ctx.globalAlpha = alpha;
    ctx.font = `${poids} ${taille}px ${POLICE}`;
    ctx.fillStyle = coul; ctx.textAlign = align; ctx.textBaseline = base;
    if (espace && "letterSpacing" in ctx) ctx.letterSpacing = `${espace}px`;
    ctx.fillText(t, x, y);
    if ("letterSpacing" in ctx) ctx.letterSpacing = "0px";
    ctx.globalAlpha = 1;
  }
  function boite(ctx, x, y, w, h, r) {
    ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }
  function pastille(ctx, t, x, y, { coul = CIEL, fond = "rgba(169, 200, 238, 0.1)", taille = 11, alpha = 1, align = "left" } = {}) {
    ctx.font = `700 ${taille}px ${POLICE}`;
    const w = ctx.measureText(t).width + 16, h = taille + 10;
    const x0 = align === "center" ? x - w / 2 : align === "right" ? x - w : x;
    ctx.globalAlpha = alpha;
    boite(ctx, x0, y - h / 2, w, h, h / 2); ctx.fillStyle = fond; ctx.fill(); ctx.strokeStyle = coul; ctx.lineWidth = 1; ctx.stroke();
    texte(ctx, t, x0 + 8, y + 0.5, { taille, coul, base: "middle", alpha });
    return w;
  }
  function hexagone(ctx, x, y, r) {          // pointy-top
    ctx.beginPath();
    for (let i = 0; i < 6; i++) { const a = (-90 + 60 * i) * RAD; ctx[i ? "lineTo" : "moveTo"](x + r * Math.cos(a), y + r * Math.sin(a)); }
    ctx.closePath();
  }
  function losange(ctx, x, y, r) { ctx.beginPath(); ctx.moveTo(x, y - r); ctx.lineTo(x + r, y); ctx.lineTo(x, y + r); ctx.lineTo(x - r, y); ctx.closePath(); }
  function bezier(a, c, b, t) { const u = 1 - t; return { x: u * u * a.x + 2 * u * t * c.x + t * t * b.x, y: u * u * a.y + 2 * u * t * c.y + t * t * b.y }; }

  // ------------------------------------------------------------------ the step player, shared by both panels
  function lecteur(section, scene) {
    const canvas = section.querySelector("canvas"), ctx = canvas.getContext("2d");
    const items = [...section.querySelectorAll(".hw-etapes li")];
    const btnLecture = section.querySelector(".hw-lecture"), btnRejouer = section.querySelector(".hw-rejouer");
    const etat = { i: 0, ecoule: 0, horloge: 0, pause: reduit, visible: false, W: 0, H: 0, fin: 0 };
    let raf = 0, avant = 0;
    // le récit sous l'animation : quelques phrases par étape (data-recit, séparées par "|"), qui défilent avec elle ;
    // une étape dure au moins le temps de lire ses phrases
    const recit = section.querySelector(".hw-recit");
    const phrases = items.map((li) => (li.dataset.recit || "").split("|").map((x) => x.trim()).filter(Boolean));
    scene.durees = scene.durees.map((d, j) => Math.max(d, phrases[j].length * 4300));
    let phraseMontree = "";
    function raconter(k) {
      const liste = phrases[etat.i];
      if (!recit || !liste.length) return;
      const n = reduit ? -1 : Math.min(liste.length - 1, Math.floor(k * liste.length));
      const cle = `${etat.i}:${n}`;
      if (cle === phraseMontree) return;
      phraseMontree = cle;
      recit.classList.remove("montre");
      void recit.offsetWidth;                                         // relance la transition
      recit.innerHTML = `<b>${etat.i + 1}/${items.length}</b> ` + (n < 0 ? liste.join(" ") : liste[n]);
      recit.classList.add("montre");
    }

    function dimensionner() {
      const r = canvas.getBoundingClientRect(), dpr = Math.min(2, window.devicePixelRatio || 1);
      etat.W = r.width; etat.H = r.height;
      canvas.width = Math.round(r.width * dpr); canvas.height = Math.round(r.height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (!raf) dessiner();
    }
    function dessiner() {
      const k = reduit ? 1 : borne(etat.ecoule / scene.durees[etat.i]);
      ctx.clearRect(0, 0, etat.W, etat.H);
      scene.dessiner(ctx, etat.W, etat.H, etat.i, k, etat.horloge, etat);
      if (section.dataset.etape !== String(etat.i)) section.dataset.etape = etat.i;
      raconter(k);
      items.forEach((li, j) => {
        li.classList.toggle("actif", j === etat.i);
        li.classList.toggle("fait", j < etat.i);
        li.querySelector("i").style.setProperty("--p", j < etat.i ? 1 : j === etat.i ? k : 0);
      });
    }
    function image(t) {
      const dt = Math.min(64, t - (avant || t)); avant = t;
      if (!etat.pause) {
        etat.horloge += dt;
        etat.ecoule += dt;
        if (etat.ecoule >= scene.durees[etat.i]) {
          if (etat.i < scene.durees.length - 1) { etat.i++; etat.ecoule = 0; }
          else if ((etat.fin += dt) > 4500) { etat.i = 0; etat.ecoule = 0; etat.fin = 0; }    // a pause, then it loops
        }
      }
      dessiner();
      raf = etat.visible ? requestAnimationFrame(image) : 0;
    }
    const lancer = () => { if (!raf && etat.visible) { avant = 0; raf = requestAnimationFrame(image); } };
    function aller(i) {
      etat.i = i; etat.ecoule = 0; etat.fin = 0;
      if (!reduit) { etat.pause = false; majBouton(); }
      lancer(); dessiner();
    }
    function majBouton() {
      btnLecture.textContent = etat.pause ? "▶" : "❚❚";
      btnLecture.setAttribute("aria-label", etat.pause ? "Play" : "Pause");
    }
    items.forEach((li, j) => li.querySelector("button").addEventListener("click", () => aller(j)));
    btnLecture.addEventListener("click", () => { etat.pause = !etat.pause; majBouton(); lancer(); });
    btnRejouer.addEventListener("click", () => aller(0));
    majBouton();
    new ResizeObserver(dimensionner).observe(canvas);
    new IntersectionObserver(([e]) => { etat.visible = e.isIntersecting; lancer(); }, { threshold: 0.25 }).observe(canvas);
    if (scene.interactions) scene.interactions(canvas, etat);
    dimensionner();
    return { aller };
  }

  // ================================================================== 1. PRE-PROCESSING
  function scenePretraitement() {
    const PAS = 3;
    const px = raster(PAS, PALETTES.earth, 0);
    const res1 = H.getRes0Cells().flatMap((c) => H.cellToChildren(c, 1));
    const bords = res1.map((c) => H.cellToBoundary(c));
    const centres = res1.map((c) => H.cellToLatLng(c));
    const CIBLE = H.latLngToCell(-23.5, -69, 1);                     // around the Atacama desert
    const iCible = res1.indexOf(CIBLE);
    const [latC, lonC] = H.cellToLatLng(CIBLE);
    // les mesures gardées pour cette cellule (illustration), une par module
    const MESURES = [
      { m: 0, nom: "mean slope", v: 4.2, f: (x) => `${x.toFixed(1)}°` },
      { m: 0, nom: "flat ground", v: 61, f: (x) => `${nb.format(x)} %` },
      { m: 1, nom: "ground, day", v: 41, f: (x) => `${nb.format(x)} °C` },
      { m: 1, nom: "ground, night", v: 8, f: (x) => `${nb.format(x)} °C` },
      { m: 2, nom: "basalt", v: 12, f: (x) => `${nb.format(x)} %` },
      { m: 4, nom: "ground ice", v: 0, f: (x) => `${nb.format(x)} %` },
    ];
    // des lignes de la table : de vrais identifiants H3 de résolution 5
    const lignes = Array.from({ length: 24 }, (_, i) => {
      const la = -55 + 130 * hache(i, 1), lo = -180 + 360 * hache(i, 2);
      return { h3: H.latLngToCell(la, lo, 5), v: [hache(i, 3) * 25, hache(i, 4) * 90, -20 + hache(i, 5) * 65, -40 + hache(i, 6) * 45, hache(i, 7) * 60, hache(i, 8) * 40] };
    });
    const COLONNES = ["h3", "slope", "flat", "day", "night", "basalt", "ice"];
    const vue = { lat0: 12, lon0: -20, glisse: 0, dernierGlisse: -1e9, mix: 0 };
    let couleurReelle = null;
    echantillonneur(TUILES_TERRE, true).then((f) => (couleurReelle = recolorer(px, f)));

    function disposition(W, H_, m) {
      const etroit = W < 640;
      const plein = etroit ? { x: W / 2, y: H_ * 0.5, R: Math.min(H_ * 0.38, W * 0.4) } : { x: W * 0.5, y: H_ * 0.52, R: Math.min(H_ * 0.4, W * 0.28) };
      const cote = etroit ? { x: W * 0.17, y: H_ * 0.17, R: Math.min(W * 0.13, H_ * 0.13) } : { x: W * 0.22, y: H_ * 0.52, R: Math.min(H_ * 0.34, W * 0.18) };
      const zone = etroit ? { x0: 14, x1: W - 14, y0: H_ * 0.34, y1: H_ - 30 } : { x0: W * 0.43, x1: W - 22, y0: 52, y1: H_ - 34 };
      return { etroit, G: { x: melange(plein.x, cote.x, m), y: melange(plein.y, cote.y, m), R: melange(plein.R, cote.R, m) }, zone };
    }

    return {
      durees: [5200, 5200, 7000, 7500],
      interactions(canvas) {
        let x0 = null;
        canvas.addEventListener("pointerdown", (e) => { x0 = e.clientX; canvas.setPointerCapture(e.pointerId); });
        canvas.addEventListener("pointermove", (e) => {
          if (x0 == null) return;
          vue.glisse -= (e.clientX - x0) * 0.45; x0 = e.clientX; vue.dernierGlisse = performance.now();
        });
        const fin = () => { x0 = null; };
        canvas.addEventListener("pointerup", fin); canvas.addEventListener("pointercancel", fin);
      },
      dessiner(ctx, W, H_, i, k, t) {
        // le globe tourne seul, se laisse tourner, puis se tourne vers la cellule scannée (étapes 3 et 4)
        const focus = i >= 2;
        vue.mix += ((focus ? 1 : 0) - vue.mix) * 0.06;
        if (reduit) vue.mix = focus ? 1 : 0;
        const libre = { lat0: 12, lon0: -20 - t * 0.006 + vue.glisse };
        const vise = { lat0: latC * 0.6, lon0: lonC + 25 };
        let dl = ((vise.lon0 - libre.lon0) % 360 + 540) % 360 - 180;
        vue.lat0 = melange(libre.lat0, vise.lat0, douce(vue.mix));
        vue.lon0 = libre.lon0 + dl * douce(vue.mix);
        const { etroit, G, zone } = disposition(W, H_, douce(vue.mix));
        G.lat0 = vue.lat0; G.lon0 = vue.lon0;

        // étape 1 : les pixels apparaissent, un satellite passe
        const revele = i === 0 ? k * 2.6 : 3;
        const ecran = globe(ctx, G, px, PAS, 1, (p) => fenetre(revele - p.ordre, 0, 0.15) * (i >= 1 ? 0.75 : 1));
        if (i === 0 || (i === 1 && k < 0.3)) {
          const a = t * 0.0011, al = i === 0 ? 1 : 1 - k / 0.3;
          const sx = G.x + Math.cos(a) * G.R * 1.28, sy = G.y + Math.sin(a) * G.R * 0.42 - G.R * 0.2;
          if (Math.sin(a) > -0.2) {
            ctx.globalAlpha = 0.18 * al; ctx.fillStyle = CIEL;
            ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(G.x + Math.cos(a) * G.R * 0.75 - 14, G.y + Math.sin(a) * G.R * 0.3);
            ctx.lineTo(G.x + Math.cos(a) * G.R * 0.75 + 14, G.y + Math.sin(a) * G.R * 0.3); ctx.closePath(); ctx.fill();
            ctx.globalAlpha = al; ctx.fillStyle = "#E9EEF5"; ctx.fillRect(sx - 4, sy - 3, 8, 6);
            ctx.fillStyle = CIEL; ctx.fillRect(sx - 15, sy - 2, 9, 4); ctx.fillRect(sx + 6, sy - 2, 9, 4); ctx.globalAlpha = 1;
          }
          const sources = ["MODIS", "MERRA-2", "LRO Diviner", "MOLA", "EMIT", "ESA CCI"];
          let x = 16;
          sources.forEach((s, j) => { const a2 = i === 0 ? fenetre(k, 0.15 + j * 0.08, 0.3 + j * 0.08) : al; x += pastille(ctx, s, x, 22, { alpha: a2 }) + 6; });
        }
        // étape 2 : la grille H3 se pose, du sud au nord ; une cellule s'allume
        if (i >= 1) {
          const kk = i === 1 ? k : 1;
          cellules(ctx, ecran, bords, (j) => {
            const a = fenetre(kk * 1.6 - (centres[j][0] + 90) / 180 * 0.8, 0, 0.25);
            if (j === iCible && (i >= 2 || kk > 0.65)) return { alpha: 1, fill: "#FFFFFF", fillAlpha: 0.25 + 0.2 * Math.sin(t / 220), trait: "#FFFFFF", epaisseur: 2 };
            return { alpha: a * (i >= 2 ? 0.45 : 0.8) };
          });
          if (i === 1) {
            texte(ctx, nb.format(613252 * sortie(fenetre(k, 0.2, 0.85))), 16, H_ - 40, { taille: 26, poids: 900, alpha: fenetre(k, 0.1, 0.3) });
            texte(ctx, "land cells on Earth · real ones are 2,400× smaller than drawn", 16, H_ - 20, { taille: 12, poids: 600, coul: DOUX, alpha: fenetre(k, 0.1, 0.3) });
          }
        }
        const centreCible = ecran(latC, lonC);

        // étape 3 : zoom sur la cellule, ses pixels lus un par un
        const aHex = i === 2 ? fenetre(k, 0.05, 0.2) : i === 3 ? 1 - fenetre(k, 0, 0.25) : 0;
        const zw = zone.x1 - zone.x0, zh = zone.y1 - zone.y0;
        const rh = etroit ? Math.min(zw * 0.24, zh * 0.42) : Math.min(zw * 0.24, zh * 0.4);
        const hx = zone.x0 + rh * 1.02, hy = etroit ? zone.y0 + zh * 0.45 : zone.y0 + zh * 0.48;
        if (aHex > 0) {
          ctx.globalAlpha = aHex * 0.6; ctx.setLineDash([4, 5]); ctx.strokeStyle = "#FFFFFF"; ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(centreCible.x, centreCible.y); ctx.lineTo(hx - rh * 0.87, hy); ctx.stroke(); ctx.setLineDash([]);
          const s = rh / 6.5, pts = [];
          for (let y = hy - rh + s / 2; y < hy + rh; y += s) {
            for (let x = hx - rh + s / 2; x < hx + rh; x += s) {
              const dx = Math.abs(x - hx), dy = Math.abs(y - hy);
              if (dx <= rh * 0.866 - s * 0.3 && dy <= rh - dx / Math.sqrt(3) - s * 0.3) pts.push({ x, y });
            }
          }
          const lus = i === 2 ? Math.floor(fenetre(k, 0.18, 0.8) * pts.length) : pts.length;
          pts.forEach((p, j) => {
            const la = latC - (p.y - hy) / rh * 4, lo = lonC + (p.x - hx) / rh * 4;
            if (!p.coul || p.reel !== !!couleurReelle) {
              p.reel = !!couleurReelle;
              const v = borne(0.75 * champ(la, lo, 9, 3) + 0.25), [r, g, b] = degrade(PALETTES.earth, v);
              p.coul = couleurReelle ? couleurReelle(la, lo) : `rgb(${r},${g},${b})`;
            }
            ctx.globalAlpha = aHex * (j < lus ? 1 : 0.18);
            ctx.fillStyle = p.coul; ctx.fillRect(p.x - s / 2 + 0.5, p.y - s / 2 + 0.5, s - 1, s - 1);
          });
          if (i === 2 && lus < pts.length) {
            const p = pts[lus];
            ctx.globalAlpha = aHex; ctx.strokeStyle = "#FFFFFF"; ctx.lineWidth = 2; ctx.strokeRect(p.x - s / 2, p.y - s / 2, s, s);
            ctx.globalAlpha = aHex * 0.25; ctx.fillStyle = "#FFFFFF"; ctx.fillRect(hx - rh, p.y - s / 2, rh * 2, s);
          }
          ctx.globalAlpha = aHex; hexagone(ctx, hx, hy, rh); ctx.strokeStyle = "#FFFFFF"; ctx.lineWidth = 2; ctx.stroke(); ctx.globalAlpha = 1;
          texte(ctx, `${nb.format(i === 2 ? lus * 1840 : pts.length * 1840)} pixels read`, hx, hy + rh + 22, { taille: 12, poids: 700, coul: DOUX, align: "center", alpha: aHex });
          // ce qu'on garde : quelques nombres
          const lx = etroit ? hx + rh * 1.1 : hx + rh * 1.25, ly0 = hy - (MESURES.length - 1) * 15;
          MESURES.forEach((m, j) => {
            const a = aHex * (i === 2 ? fenetre(k, 0.3 + j * 0.07, 0.4 + j * 0.07) : 1);
            const y = ly0 + j * 30, val = m.v * (i === 2 ? sortie(fenetre(k, 0.3 + j * 0.07, 0.85)) : 1);
            ctx.globalAlpha = a; ctx.fillStyle = MODULES[m.m].c; ctx.beginPath(); ctx.arc(lx + 4, y - 4, 4, 0, 2 * Math.PI); ctx.fill();
            texte(ctx, m.nom, lx + 14, y, { taille: etroit ? 11 : 12, poids: 600, coul: DOUX, alpha: a });
            texte(ctx, m.f(val), Math.min(zone.x1, lx + (etroit ? 132 : 170)), y, { taille: etroit ? 13 : 15, poids: 900, align: "right", alpha: a });
          });
        }

        // étape 4 : une ligne par cellule, dans de petites tables
        if (i === 3) {
          const cols = etroit ? COLONNES.slice(0, 5) : COLONNES;
          const tx = zone.x0, tw = zw, ty = zone.y0 + (etroit ? 6 : 30), rhl = etroit ? 19 : 22;
          const larg = cols.map((c, j) => (j === 0 ? tw * (etroit ? 0.36 : 0.3) : (tw * (etroit ? 0.64 : 0.7)) / (cols.length - 1)));
          const xs = larg.reduce((a, w, j) => (a.push(j ? a[j - 1] + larg[j - 1] : tx), a), []);
          const aT = fenetre(k, 0.12, 0.3);
          texte(ctx, `${nb.format(613252 * sortie(fenetre(k, 0.3, 0.95) ** 2))} rows`, tx, ty - 10, { taille: 13, poids: 800, alpha: aT });
          texte(ctx, "6 Parquet files · one per module", tx + tw, ty - 10, { taille: 11, poids: 600, coul: DOUX, align: "right", alpha: aT });
          ctx.globalAlpha = aT; ctx.fillStyle = "rgba(169, 200, 238, 0.1)"; ctx.fillRect(tx, ty, tw, rhl);
          cols.forEach((c, j) => texte(ctx, c, xs[j] + 6, ty + rhl / 2 + 1, { taille: 11, poids: 800, coul: CIEL, base: "middle", alpha: aT }));
          const visibles = Math.floor((etroit ? zone.y1 - ty - 60 : zone.y1 - ty - 64) / rhl) - 1;
          const n = 1 + Math.floor(sortie(fenetre(k, 0.3, 0.9)) * (lignes.length - 1));
          const debut = Math.max(0, n - visibles);
          const valeurs = (L) => [L.h3, `${L.v[0].toFixed(1)}°`, `${nb.format(L.v[1])}%`, `${nb.format(L.v[2])}°`, `${nb.format(L.v[3])}°`, `${nb.format(L.v[4])}%`, `${nb.format(L.v[5])}%`];
          const premiere = [H.latLngToCell(latC, lonC, 5), "4.2°", "61%", "41°", "8°", "12%", "0%"];
          for (let r = debut; r < n; r++) {
            const y = ty + rhl * (r - debut + 1);
            const vals = r === 0 ? premiere : valeurs(lignes[r - 1]);
            // la première ligne vient de l'hexagone
            let dx = 0, dy = 0;
            if (r === 0) { const f = 1 - sortie(fenetre(k, 0.05, 0.3)); dx = (hx - tx - tw / 2) * f; dy = (hy - y) * f; }
            ctx.globalAlpha = r === 0 ? 1 : 0.9;
            if (r === 0) { ctx.fillStyle = "rgba(255,255,255,0.12)"; ctx.fillRect(tx + dx, y + dy, tw, rhl); }
            ctx.strokeStyle = "rgba(255,255,255,0.05)"; ctx.beginPath(); ctx.moveTo(tx, y + rhl); ctx.lineTo(tx + tw, y + rhl); ctx.stroke();
            cols.forEach((_, j) => texte(ctx, vals[j], xs[j] + 6 + dx, y + rhl / 2 + 1 + dy, {
              taille: j === 0 ? 10.5 : 11.5, poids: j === 0 ? 600 : 700, coul: j === 0 ? DOUX : TEXTE, base: "middle" }));
          }
          // les autres tables, une par module
          const aF = fenetre(k, 0.55, 0.75);
          let x = tx, y = zone.y1 - (etroit ? 6 : 10);
          MODULES.forEach((m, j) => {
            const w = pastille(ctx, m.nom, x, y, { coul: m.c, fond: "rgba(255,255,255,0.04)", taille: etroit ? 9.5 : 10.5, alpha: aF * fenetre(k, 0.55 + j * 0.05, 0.65 + j * 0.05) });
            x += w + 5;
            if (x > tx + tw - 90 && j < MODULES.length - 1) { x = tx; y -= etroit ? 23 : 26; }
          });
          texte(ctx, "× Earth, Mars, Moon · DuckDB", tx + tw, zone.y1 + (etroit ? 18 : 22), { taille: 11, poids: 700, coul: CIEL, align: "right", alpha: aF });
        }
      },
    };
  }

  // ================================================================== 2. THE SEARCH (live)
  function sceneDirect() {
    const PAS = 4;
    const pxMars = raster(PAS, PALETTES.mars, 11), pxTerre = raster(PAS, PALETTES.earth, 0);
    if (window.TEXTURE_ACCUEIL_MARS) echantillonneur([window.TEXTURE_ACCUEIL_MARS], false).then((f) => recolorer(pxMars, f));
    echantillonneur(TUILES_TERRE, true).then((f) => recolorer(pxTerre, f));
    const zone = H.gridDisk(H.latLngToCell(18.4, 77.6, 1), 1);            // around Jezero (Perseverance)
    const bordsZone = zone.map((c) => H.cellToBoundary(c));
    // entonnoir d'une recherche d'exemple : cellules terrestres restantes après chaque porte
    const PORTES = [{ court: "Filters", nom: "Forests, crops", c: "#9DAAC0" }, ...MODULES];
    const RESTE = [613252, 571904, 287310, 139822, 70415, 34880, 17211, 8604];
    const EMPREINTE = [0.72, 0.35, 0.58, 0.8, 0.22, 0.46];               // the area's fingerprint, one bar per module
    const SITES = [[-24, -69], [-20.5, -67], [-48, -70], [35, -116], [75.4, -89.5], [64.8, -17], [21, -11], [-24, 15.5], [29, -13.6], [38.4, -110.8]];
    const gouttes = [];
    let derniereGoutte = 0;

    function disposition(W, H_) {
      if (W < 640) {
        const R = Math.min(W * 0.13, H_ * 0.1);
        return { etroit: true, mars: { x: W * 0.2, y: R + 40, R }, terre: { x: W * 0.62, y: R + 40, R },
          serveur: { x: 12, y: R * 2 + 70, w: W - 24, h: H_ - R * 2 - 82 } };
      }
      const R = Math.min(H_ * 0.27, W * 0.11);
      return { etroit: false, mars: { x: W * 0.12, y: H_ * 0.5, R }, terre: { x: W * 0.88, y: H_ * 0.5, R },
        serveur: { x: W * 0.23, y: H_ * 0.08, w: W * 0.54, h: H_ * 0.84 } };
    }

    return {
      durees: [5000, 4500, 9000, 6000],
      dessiner(ctx, W, H_, i, k, t) {
        const D = disposition(W, H_), S = D.serveur, et = D.etroit;
        // Mars, la zone peinte
        const ecranM = globe(ctx, { ...D.mars, lat0: 15, lon0: 77 }, pxMars, PAS);
        const peint = i === 0 ? Math.floor(fenetre(k, 0.05, 0.35) * zone.length + 0.999) : zone.length;
        cellules(ctx, ecranM, bordsZone, (j) => (j < peint ? { alpha: 1, fill: "#FFFFFF", fillAlpha: 0.45, trait: "#FFFFFF", epaisseur: 1.2 } : null));
        texte(ctx, "Mars · your area", D.mars.x, D.mars.y + D.mars.R + 18, { taille: 11, poids: 800, coul: "#E0794F", align: "center", espace: 1 });
        // la Terre, qui reçoit les résultats
        const ecranT = globe(ctx, { ...D.terre, lat0: 18, lon0: -50 + 8 * Math.sin(t / 4000) }, pxTerre, PAS, i === 3 ? 1 : 0.55);
        texte(ctx, "Earth", D.terre.x, D.terre.y + D.terre.R + 18, { taille: 11, poids: 800, coul: "#4FD1FF", align: "center", espace: 1 });

        // le serveur
        ctx.globalAlpha = 1; boite(ctx, S.x, S.y, S.w, S.h, 16);
        ctx.fillStyle = "rgba(8, 17, 32, 0.85)"; ctx.fill(); ctx.strokeStyle = TRAIT; ctx.lineWidth = 1; ctx.stroke();
        texte(ctx, "SERVER", S.x + 16, S.y + 24, { taille: 11, poids: 900, coul: CIEL, espace: 1.5 });
        if (!et) texte(ctx, "FastAPI + DuckDB", S.x + 86, S.y + 24, { taille: 11, poids: 600, coul: DOUX });
        // la table de la Terre, chargée en mémoire
        const tx = S.x + S.w - 16;
        pastille(ctx, et ? "DuckDB · 613,252 Earth cells" : "Earth table · 613,252 cells", tx, S.y + 22, { align: "right", taille: et ? 9.5 : 10.5 });

        // étape 1 : la requête part vers le serveur
        const entree = et ? { x: S.x + S.w * 0.25, y: S.y } : { x: S.x, y: S.y + S.h * 0.32 };
        if (i === 0) {
          const f = sortie(fenetre(k, 0.4, 0.95));
          const a = { x: D.mars.x, y: D.mars.y }, c = et ? { x: D.mars.x, y: S.y - 10 } : { x: (D.mars.x + entree.x) / 2, y: S.y - 10 };
          if (f > 0) {
            for (let q = 0; q < 8; q++) {
              const p = bezier(a, c, entree, Math.max(0, f - q * 0.025));
              ctx.globalAlpha = (1 - q / 8) * 0.5; hexagone(ctx, p.x, p.y, 6 - q * 0.5); ctx.fillStyle = "#FFFFFF"; ctx.fill();
            }
            const p = bezier(a, c, entree, f);
            ctx.globalAlpha = 1; hexagone(ctx, p.x, p.y, 9); ctx.fillStyle = "#FFFFFF"; ctx.fill();
            if (f < 0.98) pastille(ctx, "POST /api/search", p.x + 14, p.y - 14, { taille: 10.5, alpha: fenetre(f, 0, 0.1) });
          }
        }

        // zones dans le serveur : l'empreinte en haut (elle se replie quand les portes arrivent), les portes dessous
        const repli = i >= 3 ? 1 : i === 2 ? sortie(fenetre(k, 0, 0.12)) : 0;
        const eX = S.x + 16, eY = S.y + 44, eW = et ? S.w - 32 : S.w * 0.5;
        const eH1 = S.h * (et ? 0.3 : 0.4), eH2 = S.h * (et ? 0.16 : 0.18), eH = melange(eH1, eH2, repli);
        const pY = eY + eH2 + (et ? 44 : 50), pX0 = S.x + (et ? 14 : 26), pX1 = S.x + S.w - (et ? 14 : 26);
        const largPorte = (pX1 - pX0) / PORTES.length;

        // étape 2 : l'empreinte de la zone, une barre par module
        if (i >= 1) {
          const kk = i === 1 ? k : 1;
          texte(ctx, "Fingerprint of your area", eX, eY + 10, { taille: 12, poids: 800, alpha: fenetre(kk, 0, 0.15) });
          const bw = eW / MODULES.length, haut = eH - 22 - 16 * (1 - repli);
          MODULES.forEach((m, j) => {
            const h = haut * EMPREINTE[j] * sortie(fenetre(kk, 0.1 + j * 0.08, 0.45 + j * 0.08));
            const x = eX + j * bw + bw * 0.15, base = eY + 22 + haut;
            ctx.globalAlpha = 0.12; ctx.fillStyle = m.c; ctx.fillRect(x, eY + 22, bw * 0.7, haut);
            ctx.globalAlpha = 1; ctx.fillRect(x, base - h, bw * 0.7, h);
            texte(ctx, m.court, x + bw * 0.35, base + 4, { taille: 9.5, poids: 700, coul: DOUX, align: "center", base: "top", alpha: 1 - repli });
          });
          if (!et) {
            const a = fenetre(kk, 0.6, 0.8) * (1 - repli);
            texte(ctx, "the mean of each criterion", eX + eW + 18, eY + eH * 0.5, { taille: 12, poids: 600, coul: DOUX, alpha: a });
            texte(ctx, "over your hexagons", eX + eW + 18, eY + eH * 0.5 + 17, { taille: 12, poids: 600, coul: DOUX, alpha: a });
          }
        }

        // étape 3 : les cellules de la Terre traversent les portes, celles qui ressemblent moins tombent
        if (i >= 2) {
          const kk = i === 2 ? k : 1;
          const porteAtteinte = Math.min(PORTES.length, Math.floor(kk * (PORTES.length + 0.6)));
          // gouttes (cellules de la Terre) : naissent à gauche, avancent, tombent à la porte qu'elles ratent
          if (i === 2 && !reduit && t - derniereGoutte > 28) {
            derniereGoutte = t;
            gouttes.push({ x: pX0 - 6, y: pY + (hache(t, 1) - 0.5) * 10, u: hache(t, 2), vy: 0, morte: false, a: 1 });
          }
          const front = pX0 + largPorte * (porteAtteinte + 0.15);
          for (let g = gouttes.length - 1; g >= 0; g--) {
            const d = gouttes[g];
            if (!d.morte) {
              d.x += 1.6;
              const porte = Math.floor((d.x - pX0) / largPorte);
              if (porte >= 0 && porte < PORTES.length && d.x - pX0 - porte * largPorte > largPorte * 0.45) {
                const garde = (RESTE[porte + 1] / RESTE[0]) ** 0.42;
                if (d.u > garde) d.morte = true;
              }
              if (d.x > Math.min(front, pX1 + 8)) d.x = Math.min(front, pX1 + 8), d.a -= 0.05;
            } else { d.vy += 0.25; d.y += d.vy; d.a -= 0.035; }
            if (d.a <= 0 || i !== 2) { gouttes.splice(g, 1); continue; }
            ctx.globalAlpha = d.a * (d.morte ? 0.6 : 0.9); ctx.fillStyle = d.morte ? "#F2545B" : "#4FD1FF";
            ctx.beginPath(); ctx.arc(d.x, d.y, 2.2, 0, 2 * Math.PI); ctx.fill();
          }
          ctx.globalAlpha = 1;
          PORTES.forEach((p, j) => {
            const x = pX0 + largPorte * j + largPorte * 0.5, passee = j < porteAtteinte;
            const allumee = passee ? 1 : 0.25;
            ctx.globalAlpha = allumee; ctx.strokeStyle = p.c; ctx.lineWidth = passee ? 3 : 1.5;
            ctx.beginPath(); ctx.moveTo(x, pY - 22); ctx.lineTo(x, pY - 8); ctx.moveTo(x, pY + 8); ctx.lineTo(x, pY + 22); ctx.stroke();
            texte(ctx, p.court, x, pY - 30, { taille: et ? 9 : 10.5, poids: 800, coul: p.c, align: "center", alpha: allumee });
            const n = RESTE[j + 1];
            texte(ctx, n >= 10000 ? `${nb.format(n / 1000)}k` : nb.format(n), x, pY + 36, { taille: et ? 9.5 : 11, poids: 700, coul: TEXTE, align: "center", alpha: passee ? 1 : 0 });
          });
          // le compteur
          const n = porteAtteinte === 0 ? RESTE[0] : RESTE[porteAtteinte];
          const cy = Math.max(pY + (et ? 92 : 100), S.y + S.h - (et ? 20 : 28));
          texte(ctx, nb.format(n), S.x + S.w / 2, cy, { taille: et ? 20 : 26, poids: 900, align: "center" });
          texte(ctx, "Earth cells still in the race", S.x + S.w / 2, cy - (et ? 24 : 30), { taille: 11, poids: 700, coul: DOUX, align: "center" });
        }

        // étape 4 : les meilleurs sites reviennent sur la Terre
        if (i === 3) {
          const f = sortie(fenetre(k, 0, 0.35));
          const sortiePt = et ? { x: S.x + S.w * 0.75, y: S.y } : { x: S.x + S.w, y: S.y + S.h * 0.32 };
          const c = et ? { x: D.terre.x, y: S.y - 10 } : { x: (sortiePt.x + D.terre.x) / 2, y: S.y - 10 };
          if (f < 1) { const p = bezier(sortiePt, c, { x: D.terre.x, y: D.terre.y }, f); ctx.globalAlpha = 1; losange(ctx, p.x, p.y, 7); ctx.fillStyle = "#F2C14E"; ctx.fill(); }
          SITES.forEach(([la, lo], j) => {
            const a = fenetre(k, 0.35 + j * 0.04, 0.42 + j * 0.04);
            const p = ecranT(la, lo);
            if (a <= 0 || p.z < 0.1) return;
            const r = 5 * (0.6 + 0.4 * sortie(a)) * (j === 0 ? 1.3 : 1);
            ctx.globalAlpha = a; losange(ctx, p.x, p.y, r); ctx.fillStyle = j === 0 ? "#F2C14E" : "#FFFFFF"; ctx.fill();
            ctx.strokeStyle = "#081120"; ctx.lineWidth = 1; ctx.stroke();
          });
          ctx.globalAlpha = 1;
          const aT = fenetre(k, 0.6, 0.8);
          if (!et) {
            pastille(ctx, "Top 10 · ≥ 300 km apart", D.terre.x, D.terre.y - D.terre.R - 34, { align: "center", coul: "#F2C14E", fond: "rgba(242,193,78,0.1)", alpha: aT });
            texte(ctx, "≈ 2 s", D.terre.x, D.terre.y - D.terre.R - 10, { taille: 13, poids: 900, align: "center", alpha: aT });
          } else {
            texte(ctx, "Top 10 · ≈ 2 s", D.terre.x, D.terre.y + D.terre.R + 32, { taille: 11, poids: 800, coul: "#F2C14E", align: "center", alpha: aT });
          }
        }
      },
    };
  }

  if (!H) return;
  const lecteurs = {
    pretraitement: lecteur(document.getElementById("pretraitement"), scenePretraitement()),
    direct: lecteur(document.getElementById("direct"), sceneDirect()),
  };

  // les deux boutons en haut : un seul panneau visible à la fois, qui reprend du début
  const onglets = [...document.querySelectorAll(".hw-onglets [role=tab]")];
  function choisir(onglet, focus) {
    onglets.forEach((o) => {
      const oui = o === onglet, panneau = document.getElementById(o.getAttribute("aria-controls"));
      o.setAttribute("aria-selected", String(oui));
      o.tabIndex = oui ? 0 : -1;
      panneau.hidden = !oui;
    });
    if (focus) onglet.focus();
    const lecteur = lecteurs[onglet.getAttribute("aria-controls")];   // the validation tab has no animation
    if (lecteur) lecteur.aller(0);
    history.replaceState(null, "", "#" + onglet.getAttribute("aria-controls"));
  }
  onglets.forEach((o, j) => {
    o.addEventListener("click", () => choisir(o));
    o.addEventListener("keydown", (e) => {
      const d = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
      if (d) { e.preventDefault(); choisir(onglets[(j + d + onglets.length) % onglets.length], true); }
    });
  });
  const depart = onglets.find((o) => "#" + o.getAttribute("aria-controls") === location.hash) || onglets[0];
  onglets.forEach((o) => (document.getElementById(o.getAttribute("aria-controls")).hidden = o !== depart));
  onglets.forEach((o) => o.setAttribute("aria-selected", String(o === depart)));
  onglets.forEach((o) => (o.tabIndex = o === depart ? 0 : -1));
})();
