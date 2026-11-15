// Animated summary of an analog site: a separate page, opened from a site's details card (js/analogues.js).
//
// URL: bilan.html?w=<weights>&s=<score>&n=<rank>/<total>#<body>/<zone id>/<site H3 cell>
// Everything comes from the server (application/server), nothing is fabricated:
//   GET /api/zones/<id>        the painted area on Mars or the Moon
//   POST /api/search/detail    values and similarity, variable by variable (zone and site)
//   GET /api/site/<cell>       place name and site card (vegetation, mines, clouds...)
//   POST /api/search           funnel steps (number of remaining regions)
//   GET /api/presets           weight presets ("For whom?")
//   GET /api/relief            relief and image on both sides (3D slide)
// A slide is skipped when the data feeding it is missing. three.js (r147, unpkg) is loaded on the first
// 3D slide only.

(async function () {
  const q = new URLSearchParams(location.search);
  // Serveur : local (http://127.0.0.1:8000) sur cette machine ou en file://, https://api.astrowrap.earth en ligne ; ?api=... l'emporte.
  const API = (q.get("api") || (/^(localhost|127\.0\.0\.1|\[::1\]|)$/.test(location.hostname) ? "http://127.0.0.1:8000" : "https://api.astrowrap.earth")).replace(/\/$/, "");
  const H = window.h3;
  const [brut, zoneIdBrut, cellule] = location.hash.slice(1).split("/");
  const corps = { lune: "moon" }[brut] || brut;
  const NOMS = { mars: "Mars", moon: "Moon" };
  const SUR = { mars: "on Mars", moon: "on the Moon" }[corps];
  const COULEUR_CORPS = { mars: "#E0794F", moon: "#C9CED6" };
  const COULEUR_TERRE = "#4FD1FF";
  const RAYON_KM = { earth: 6371.0088, mars: 3389.5, moon: 1737.4 };
  const pct = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 0 });
  const nb = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  const nb1 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
  const nb2 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
  const NIVEAUX = [
    { min: 0.8, nom: "Very close", couleur: "#3DDC97" },
    { min: 0.6, nom: "Close", couleur: "#B9E05A" },
    { min: 0.4, nom: "Partial", couleur: "#F2C14E" },
    { min: -1, nom: "Far", couleur: "#F2545B" },
  ];
  const niveau = (s) => NIVEAUX.find((n) => s >= n.min);
  const NOMS_SIMPLES = { thermal: "Temperature", topography: "Terrain", geology: "Rocks", wind: "Wind and dust",
    volatiles: "Ice and water", astro: "Volcanoes and caves" };
  const COURTS = { lst_day_mean: "ground temperature, day", lst_night_mean: "ground temperature, night", amplitude: "day-night range",
    part_pente_inf_5: "flat ground", pentes: "typical slope", rugosite_rms: "roughness", denivele: "local elevation range",
    densite_crateres: "craters", lithologie: "rocks", mineraux: "minerals", part_oxyde_fer: "iron oxides",
    part_sol_nu: "bare ground", part_dunes: "dunes", vent_fort_rel: "strong winds", poussiere_rang: "dust", tempetes_rang: "dust storms",
    indice_glace_sol: "ground ice", part_glace_surface: "surface ice", eau_sol_rang: "soil water",
    cold_fraction: "very cold time", hot_fraction: "very hot time", daylight_fraction_min: "daylight, dark season",
    daylight_fraction_max: "daylight, bright season", volcans: "volcanoes", cavites: "caves and pits" };
  const CLASSES = { sedimentaire_clastique: "sedimentary", non_consolide: "loose sediments", volcanique_felsique: "felsic volcanic",
    plutonique_basique: "gabbro", plutonique_felsique: "granite", metamorphique: "metamorphic", evaporite: "evaporites",
    argile_al: "Al clays", argile_fe_mg: "Fe-Mg clays", silice_hydratee: "hydrated silica", mafique_autre: "other mafics",
    autre_mineral: "other", pyroxene: "pyroxene", feldspath: "plagioclase", basalte: "basalt", glace: "ice", impact: "impact breccias",
    carbonate: "carbonates", sulfate: "sulfates", sel: "salts", mica: "micas", olivine: "olivine", pyroclastique: "pyroclastic" };
  const COULEUR_CLASSE = { basalte: "#5B6C8F", volcanique_felsique: "#C9A0DC", pyroclastique: "#E07A5F", plutonique_basique: "#3D5A80",
    plutonique_felsique: "#F4A6A6", sedimentaire_clastique: "#E9C46A", non_consolide: "#F4E3B1", carbonate: "#A8DADC",
    evaporite: "#FFFFFF", metamorphique: "#8D99AE", glace: "#BDE0FE", impact: "#6D597A", pyroxene: "#2A9D8F", olivine: "#8AB17D",
    feldspath: "#E5E5E5", mafique_autre: "#52796F", argile_al: "#DDB892", argile_fe_mg: "#B08968", mica: "#CDB4DB",
    sulfate: "#FFD166", silice_hydratee: "#90E0EF", sel: "#F8F9FA", autre_mineral: "#ADB5BD" };
  // Classes que les cartes de Mars et de la Lune ont et que les données de la Terre n'ont pas (README du serveur).
  const SANS_TERRE = ["impact", "pyroxene", "olivine", "feldspath"];
  // Constantes physiques des trois corps (fiches planétaires de la NASA) : ce qu'aucun site terrestre ne reproduit.
  const PHYSIQUE = {
    mars: { g: 3.71, pression: "≈ 0.6 kPa", ptexte: "Air pressure: a thin atmosphere, mostly CO₂." },
    moon: { g: 1.62, pression: "≈ 0 kPa", ptexte: "Air pressure: no atmosphere, a vacuum." },
    earth: { g: 9.81, pression: "≈ 101 kPa" },
  };

  const echapper = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const scene = document.getElementById("b-scene");
  const racine = document.getElementById("bilan");

  function erreur(msg) {
    document.getElementById("b-attente").remove();
    scene.insertAdjacentHTML("beforeend", `<p class="etat-erreur">${msg}</p>`);
  }
  if (!["mars", "moon"].includes(corps) || !cellule || !H.isValidCell(cellule)) {
    return erreur("Incomplete address: open your AstroWrap from a site card (the “Play the AstroWrap” button).");
  }
  document.documentElement.style.setProperty("--corps", COULEUR_CORPS[corps]);

  /** Une valeur lisible : °C, %, centile, roche dominante… (même règle que la fiche du site). */
  function lisible(v, meta) {
    if (v == null) return "–";
    if (meta.mode === "hellinger") {
      const top = Object.entries(v).filter(([, x]) => x != null && x >= 0.05).sort((a, b) => b[1] - a[1]).slice(0, 2);
      return top.length ? top.map(([k, x]) => `${CLASSES[k] || k.replace(/_/g, " ")} ${pct.format(x)}`).join(", ") : "no dominant type";
    }
    if (meta.mode === "deciles") return `${nb1.format(v[Math.floor(v.length / 2)] ?? 0)}°`;
    if (meta.mode === "rang" || /_rang$/.test(meta.key)) return `percentile ${nb.format(100 * v)}`;
    if (meta.unit === "K") return meta.key === "amplitude" ? `${nb.format(v)} °C` : `${nb.format(v - 273.15)} °C`;
    if (meta.unit === "°") return `${nb1.format(v)}°`;
    if (!meta.unit && v >= 0 && v <= 1) return pct.format(v);
    return `${nb2.format(v)}${meta.unit ? " " + meta.unit : ""}`;
  }
  const nomVar = (v) => COURTS[v.key] || v.label.replace(/ \(.*\)$/, "").toLowerCase();

  // ------------------------------------------------------------------ chargement
  const json = async (chemin, corpsRequete) => {
    const r = await fetch(`${API}${chemin}`, corpsRequete ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpsRequete) } : undefined);
    if (!r.ok) throw new Error(`${chemin}: ${r.status}`);
    return r.json();
  };
  const sante = await fetch(`${API}/api/health`).then((r) => r.json()).catch(() => null);
  if (!sante) return erreur("The server does not respond. Start it (npm start in application/client), then reload the recap.");

  let zone = [];
  if (/^[0-9a-f]{12}$/.test(zoneIdBrut || "")) {
    try { zone = (await json(`/api/zones/${zoneIdBrut}`)).h3_cells || []; } catch (e) { /* repli ci-dessous */ }
  }
  if (!zone.length) {
    try { zone = (localStorage.getItem(`analogues-zone-${corps}`) || "").split(",").filter(Boolean); } catch (e) { zone = []; }
  }
  if (!zone.length) return erreur("The reference area cannot be found (the server lost its cache). Paint the area again, then reopen the recap.");

  const poids = {};
  (q.get("w") || "").split(",").forEach((p) => { const [k, v] = p.split(":"); if (k && isFinite(+v)) poids[k] = +v; });
  const filtres = q.get("v") === "0" ? {} : { max_vegetation: 0.3 };
  if (q.get("p") === "1") filtres.max_protected = 0.3;           // « Écarter les aires protégées » (analogues.js)
  const [detail, fiche, presets, recherche] = await Promise.all([
    json("/api/search/detail", { body: corps, h3_cells: zone, cell: cellule }).catch(() => null),
    json(`/api/site/${cellule}`).catch(() => null),
    json("/api/presets").catch(() => null),
    json("/api/search", { body: corps, h3_cells: zone, weights: poids, filters: filtres, top_k: 50 }).catch(() => null),
  ]);
  if (!detail || !(detail.modules || []).length) return erreur("The server could not compare this site with the area. Try again from the site card.");

  const modules = detail.modules.filter((m) => m.similarity != null);
  const poidsDe = (k) => (poids[k] ?? 1);
  /** Moyenne pondérée des ressemblances des modules qui ont une donnée. */
  const scoreAvec = (w) => {
    let s = 0, t = 0;
    modules.forEach((m) => { const x = w[m.key] ?? 0; s += x * m.similarity; t += x; });
    return t > 0 ? s / t : null;
  };
  const score = q.get("s") != null && isFinite(+q.get("s")) ? +q.get("s") : scoreAvec(Object.fromEntries(modules.map((m) => [m.key, poidsDe(m.key)])));
  const rangTexte = /^\d+\/\d+$/.test(q.get("n") || "") ? q.get("n").split("/") : null;
  const lieu = (fiche && fiche.place && fiche.place.name) || `${nb2.format(fiche ? fiche.lat : 0)}°, ${nb2.format(fiche ? fiche.lon : 0)}°`;
  const sousTitre = fiche && fiche.place ? (() => {
    const p = fiche.place;
    const m = [];
    const nat = (p.natural_regions || [])[0];
    if (nat && nat.kind) m.push(nat.kind.charAt(0).toUpperCase() + nat.kind.slice(1));
    [p.locality, p.state, p.country].forEach((x) => { if (x && x !== p.name && !m.includes(x)) m.push(x); });
    return m.join(" · ");
  })() : "";
  const variables = modules.flatMap((m) => m.variables.map((v) => ({ ...v, module: m.key })));
  const variable = (cle) => variables.find((v) => v.key === cle);
  const fait = (section, debut) => {
    const s = fiche && (fiche.sections || []).find((x) => x.name === section);
    return s ? (s.items || []).find((i) => i.label.startsWith(debut)) : null;
  };

  // ------------------------------------------------------------------ géométrie de la zone (pour le relief 3D)
  // Le carré est calculé par relief-bilan.js, comme sur la page principale qui l'a préchargé.
  const RB = window.reliefBilan;
  const cellulesZone = RB.cellules6(zone);
  const echelleSurface = (RAYON_KM[corps] / RAYON_KM.earth) ** 2;       // h3 mesure sur la Terre : on ramène au corps
  const surfaceZone = cellulesZone.reduce((s, c) => s + H.cellArea(c, "km2"), 0) * echelleSurface;
  const cadre = RB.cadre(cellulesZone, corps);

  // ------------------------------------------------------------------ petits composants
  const motNiveau = (s) => { const n = niveau(s); return `<span class="mot" style="--c:${n.couleur}">${n.nom}</span>`; };
  const tete = (kicker, titre) => `<div class="tete"><p class="kicker a" style="--i:0">${kicker}</p><h2 class="a" style="--i:1">${titre}</h2></div>`;
  const compteur = (valeur, format, classe = "") => `<b class="${classe}" data-n="${valeur}" data-f="${format}">${formater(valeur, format)}</b>`;
  function formater(v, f) {
    if (f === "pct") return pct.format(v);
    if (f === "int") return nb.format(v);
    if (f === "dec1") return nb1.format(v);
    if (f === "m") return `${nb.format(v)} m`;
    return String(v);
  }
  const barreParts = (parts) => Object.entries(parts || {}).filter(([, x]) => x != null && x > 0.005).sort((a, b) => b[1] - a[1])
    .map(([k, x]) => `<i style="width:${100 * x}%;background:${COULEUR_CLASSE[k] || "#999"}" title="${CLASSES[k] || k} ${pct.format(x)}"></i>`).join("");
  /** Position de v sur l'échelle de la variable (0 à 100), pour les barres miroir. */
  const echelle = (v) => {
    const a = v.mode === "deciles" ? (v.reference || [])[4] : v.reference;
    const b = v.mode === "deciles" ? (v.earth || [])[4] : v.earth;
    let [lo, hi] = v.range || [0, 1];
    [a, b].forEach((x) => { if (x != null) { lo = Math.min(lo, x); hi = Math.max(hi, x); } });
    const pos = (x) => (x == null || hi <= lo ? 0 : 100 * (x - lo) / (hi - lo));
    return [pos(a), pos(b), a, b];
  };
  const absent = (v) => v.mode === "abs" && !v.unit && typeof v.earth === "number" && typeof v.reference === "number" && v.earth <= 0.01 && v.reference <= 0.01;

  function ligneMiroir(v, i, avecSens) {
    const [pa, pb, a, b] = echelle(v);
    let sens = "";
    if (avecSens && typeof a === "number" && typeof b === "number") {
      if (v.unit === "K" && v.key !== "amplitude") sens = `${b > a ? "+" : "−"}${nb.format(Math.abs(b - a))} °C on Earth`;
      else sens = b > a ? "higher on Earth" : "lower on Earth";
    }
    return `<div class="m-l a" style="--i:${i + 2}">
      <div class="m-titre">${echapper(nomVar(v))}</div>
      <div class="m-corps">
        <span class="m-val g">${echapper(lisible(v.reference, v))}</span>
        <span class="m-barre g" style="--i:${i}"><i style="--w:${pa}%"></i></span>
        <span class="m-barre d" style="--i:${i}"><i style="--w:${pb}%"></i></span>
        <span class="m-val d">${echapper(lisible(v.earth, v))}</span>
      </div>
      ${sens ? `<div class="m-sens">${sens}</div>` : ""}</div>`;
  }

  // ------------------------------------------------------------------ les diapositives
  const diapos = [];
  const ajouter = (d) => { if (d) diapos.push(d); };

  // 1. Qui contre qui
  ajouter({
    cle: "intro", duree: 9000,
    html: `<div class="tete"><p class="kicker a" style="--i:0">Your area ${SUR} · a site on Earth</p></div>
      <div class="corps duo">
        <div class="cote g aG" style="--i:1"><span class="qui">${NOMS[corps]} · your area</span>
          <span class="gros">${NOMS[corps].toUpperCase()}</span>
          <span class="petit">${nb.format(surfaceZone)} km² painted · ${nb.format(cellulesZone.length)} tiles</span></div>
        <div class="diviseur a" style="--i:0"><div class="jeton" style="--c:${score != null ? niveau(score).couleur : "#fff"}">
          ${score != null ? `${compteur(score, "pct")}<span>${niveau(score).nom}</span>` : "<span>≈</span>"}</div></div>
        <div class="cote d aD" style="--i:2"><span class="qui">Earth${rangTexte ? ` · site ${rangTexte[0]} of ${rangTexte[1]}` : ""}</span>
          <span class="gros nom">${echapper(lieu)}</span>
          <span class="petit">${echapper(sousTitre)}${fiche ? `${sousTitre ? " · " : ""}${nb2.format(Math.abs(fiche.lat))}° ${fiche.lat >= 0 ? "N" : "S"}, ${nb2.format(Math.abs(fiche.lon))}° ${fiche.lon >= 0 ? "E" : "W"}` : ""}</span></div>
      </div>
      <p class="note pied a" style="--i:4">Similarity: weighted average of the criteria measured on both bodies. Click or use ‹ › to move on.</p>`,
  });

  // 2. L'entonnoir
  const etapes = recherche ? recherche.funnel.filter((e) => e.type === "progress") : [];
  if (etapes.length >= 3) {
    const max = Math.max(...etapes.map((e) => e.cells_remaining), 1);
    const larg = (n) => Math.max(2, 100 * Math.log10(Math.max(n, 1)) / Math.log10(max));
    const nomEtape = (e) => (e.stage === "start" ? "Land" : e.stage === "filters" ? "No forests or crops" : NOMS_SIMPLES[e.module] || e.module);
    const lignes = etapes.slice(0, 8).map((e, i) => `<div class="fun-l a" style="--i:${i + 1}"><span class="nom">${echapper(nomEtape(e))}</span>
      <span class="piste" style="--i:${i}"><i style="--w:${larg(e.cells_remaining)}%"></i></span>${compteur(e.cells_remaining, "int", "n")}</div>`).join("");
    const nFinal = recherche.funnel.filter((e) => e.type === "done").map((e) => e.cells_remaining)[0];
    ajouter({
      cle: "entonnoir", duree: 9000,
      html: `${tete("How we got here", `${nb.format(etapes[0].cells_remaining)} regions of the Earth, <em>one site</em>`)}
        <div class="corps fun">${lignes}
          ${nFinal != null ? `<div class="fun-l a" style="--i:${etapes.length + 1}"><span class="nom"><b>Ranking</b></span>
            <span class="piste" style="--i:${etapes.length}"><i style="--w:${larg(nFinal)}%"></i></span>${compteur(nFinal, "int", "n")}</div>` : ""}</div>
        <p class="note pied a" style="--i:${etapes.length + 3}">Each criterion sets aside the regions that look less like your area than the Earth median. The scale is logarithmic.${rangTexte ? ` This site is #${rangTexte[0]} of the ${rangTexte[1]} selected (at least 300 km apart).` : ""}</p>`,
    });
  }

  // 3. Les critères, en radar
  if (modules.length >= 1) {
    const N = modules.length;
    const R = 150, C = 200;
    const pt = (i, r) => [C + r * Math.sin((2 * Math.PI * i) / N), C - r * Math.cos((2 * Math.PI * i) / N)];
    const anneaux = [0.25, 0.5, 0.75, 1].map((f) => `<polygon class="radar-anneau" points="${modules.map((_, i) => pt(i, R * f).join(",")).join(" ")}"/>`).join("");
    const axes = modules.map((_, i) => `<line class="radar-axe" x1="${C}" y1="${C}" x2="${pt(i, R)[0]}" y2="${pt(i, R)[1]}"/>`).join("");
    const forme = modules.map((m, i) => pt(i, R * Math.max(0.02, m.similarity)).join(",")).join(" ");
    const points = modules.map((m, i) => { const [x, y] = pt(i, R * Math.max(0.02, m.similarity)); return `<circle cx="${x}" cy="${y}" r="7" fill="${niveau(m.similarity).couleur}" stroke="#081120" stroke-width="2"/>`; }).join("");
    const etiq = modules.map((m, i) => {
      const [x, y] = pt(i, R + 30);
      const ancre = Math.abs(x - C) < 8 ? "middle" : x > C ? "start" : "end";
      return `<text class="radar-etiq" x="${x}" y="${y + 5}" text-anchor="${ancre}">${echapper(NOMS_SIMPLES[m.key] || m.name)}</text>`;
    }).join("");
    const tri = modules.slice().sort((a, b) => b.similarity - a.similarity);
    ajouter({
      cle: "criteres", duree: 9000,
      html: `${tete("Criterion by criterion", `Where it <em>matches</em>`)}
        <div class="corps radar-zone">
          <svg viewBox="-110 -10 620 420" role="img" aria-label="Similarity by criterion">${anneaux}${axes}
            <g class="radar-forme"><polygon points="${forme}" fill="rgba(242,193,78,0.22)" stroke="#F2C14E" stroke-width="3" stroke-linejoin="round"/>${points}</g>${etiq}</svg>
          <div class="liste-crit">${tri.map((m, i) => `<div class="crit a" style="--i:${i + 2};--c:${niveau(m.similarity).couleur}">
            <span>${echapper(NOMS_SIMPLES[m.key] || m.name)}<span class="mot">${niveau(m.similarity).nom}${m.variables.some((v) => !v.compared) ? " · partial comparison" : ""}</span></span>
            ${compteur(m.similarity, "pct", "p")}</div>`).join("")}</div>
        </div>
        <p class="note pied a" style="--i:8">The wider the shape, the more the site looks like your area ${SUR}. A criterion without data is not shown.</p>`,
    });
  }

  // 4. Le relief en 3D (seulement s'il se ressemble)
  const topo = modules.find((m) => m.key === "topography");
  const plat = variable("part_pente_inf_5");
  let relief3D = null;
  if (topo && topo.similarity >= 0.6 && fiche) {
    const demande = (b, lat, lon) => json(RB.chemin(b, lat, lon, cadre.taille)).then((d) => d, (e) => e);
    relief3D = { cote: [demande(corps, cadre.lat, cadre.lon), demande("earth", fiche.lat, fiche.lon)] };
    const cote = (i, b, nom) => `<figure class="${i ? "d" : "g"} ${i ? "aD" : "aG"}" style="--i:1"><figcaption>${nom}</figcaption>
      <div class="sc" id="b3-${i}"><p class="vide">Loading the terrain…</p></div>
      <div class="stat" id="b3s-${i}"></div></figure>`;
    ajouter({
      cle: "relief", duree: 18000, trois: true,
      html: `${tete(`Terrain · ${motNiveau(topo.similarity)}`, `Terrain <em>that matches</em>`)}
        <div class="corps trois">${cote(0, corps, `${NOMS[corps]} · your area`)}${cote(1, "earth", `Earth · ${echapper(lieu)}`)}</div>
        <p class="note pied a" style="--i:4">The same ${nb.format(cadre.taille)} km square on both sides, same scale, same vertical exaggeration. Drag to rotate: the other one follows.${plat && plat.compared ? ` Flat ground (< 5°): ${lisible(plat.reference, plat)} ${SUR}, ${lisible(plat.earth, plat)} here.` : ""}</p>`,
    });
  }

  // 5. Température
  const jour = variable("lst_day_mean"), nuit = variable("lst_night_mean"), amp = variable("amplitude");
  if (jour && nuit && jour.reference != null && jour.earth != null && nuit.reference != null && nuit.earth != null) {
    const c = (k) => k - 273.15;
    const tous = [jour.reference, jour.earth, nuit.reference, nuit.earth].map(c);
    const lo = Math.min(-100, Math.floor(Math.min(...tous) / 10) * 10 - 10), hi = Math.max(60, Math.ceil(Math.max(...tous) / 10) * 10 + 10);
    const h = (x) => `${(100 * (x - lo)) / (hi - lo)}%`;
    const th = (x, nom, i) => `<div class="th"><span class="th-val">${nb.format(x)}°</span>
      <span class="th-tube"><i style="--h:${h(x)};--i:${i}"></i><span class="th-zero" style="bottom:${h(0)}"></span></span><span class="th-nom">${nom}</span></div>`;
    const lien = modules.find((m) => m.key === "thermal");
    ajouter({
      cle: "thermique", duree: 9000,
      html: `${tete(`Ground temperature${lien ? ` · ${motNiveau(lien.similarity)}` : ""}`, `Warm by day, <em>cold at night</em>`)}
        <div class="corps thermos">
          <div class="thermo-cote aG" style="--c:var(--g);--i:1"><span class="qui">${NOMS[corps]} · your area</span>
            <div class="thermo-paire">${th(c(jour.reference), "day", 0)}${th(c(nuit.reference), "night", 1)}</div></div>
          <div class="thermo-cote aD" style="--c:var(--d);--i:2"><span class="qui">Earth · ${echapper(lieu)}</span>
            <div class="thermo-paire">${th(c(jour.earth), "day", 2)}${th(c(nuit.earth), "night", 3)}</div></div>
        </div>
        <p class="note pied a" style="--i:5">Average ground temperature (°C). Dotted line: 0 °C. ${amp && amp.reference != null ? `Day-night range: ${nb.format(amp.reference)} °C ${SUR}, ${nb.format(amp.earth)} °C here.` : ""}</p>`,
    });
  }

  // 6. Roches
  const compositions = variables.filter((v) => v.mode === "hellinger" && v.reference && v.earth);
  if (compositions.length) {
    const blocs = compositions.map((v, k) => {
      const classes = [...new Set([...Object.keys(v.reference), ...Object.keys(v.earth)])]
        .filter((c) => (v.reference[c] || 0) >= 0.03 || (v.earth[c] || 0) >= 0.03);
      const manque = SANS_TERRE.filter((c) => (v.reference[c] || 0) >= 0.05).map((c) => CLASSES[c]);
      return `<div class="parts-bloc a" style="--i:${k + 1}"><div class="m-titre">${echapper(nomVar(v))}</div>
        <div class="parts-ligne" style="--c:var(--g)"><span class="qui">${NOMS[corps]} · your area</span><div class="pile" style="--i:${2 * k}">${barreParts(v.reference)}</div></div>
        <div class="parts-ligne" style="--c:var(--d)"><span class="qui">Earth · ${echapper(lieu)}</span><div class="pile" style="--i:${2 * k + 1}">${barreParts(v.earth)}</div></div>
        <div class="legende">${classes.map((c) => `<span style="--k:${COULEUR_CLASSE[c] || "#999"}">${CLASSES[c] || c}</span>`).join("")}</div>
        ${!v.compared ? `<p class="note">Not comparable${manque.length ? `: the Earth data have no “${manque.join(", ")}” class` : ": classes missing from the Earth data"}.</p>` : ""}</div>`;
    }).join("");
    const geo = modules.find((m) => m.key === "geology");
    const partielle = compositions.some((v) => !v.compared);
    ajouter({
      cle: "roches", duree: 9000,
      html: `${tete(`Rocks${geo ? ` · ${partielle ? '<span class="mot" style="--c:#9DAAC0">partial comparison</span>' : motNiveau(geo.similarity)}` : ""}`, `What the <em>ground is made of</em>`)}<div class="corps parts-bloc">${blocs}</div>
        <p class="note pied a" style="--i:6">Share of each class in the area and in the selected cell. Only the classes present on both sides are compared.</p>`,
    });
  }

  // 7 et 8. Ce qui se ressemble, ce qui change
  const comparables = variables.filter((v) => v.compared && v.similarity != null && v.mode !== "hellinger");
  const choisir = (liste, n) => {
    const par = {};
    return liste.filter((v) => { par[v.module] = (par[v.module] || 0) + 1; return par[v.module] <= 2; }).slice(0, n);
  };
  const proches = choisir(comparables.filter((v) => v.similarity >= 0.8)
    .sort((a, b) => (b.similarity - (absent(b) ? 0.15 : 0)) - (a.similarity - (absent(a) ? 0.15 : 0))), 4);
  const loins = choisir(comparables.filter((v) => v.similarity < 0.4).sort((a, b) => a.similarity - b.similarity), 4);
  const noteRang = (liste) => (liste.some((v) => v.mode === "rang" || /_rang$/.test(v.key)) ? " “Percentile”: the rank of the value among the cells of each body." : "");
  const legendeMiroir = `<div class="m-corps a" style="--i:1;font-size:12px;font-weight:800;letter-spacing:.14em;text-transform:uppercase">
    <span style="text-align:right;color:var(--g)">${NOMS[corps]}</span><span></span><span></span><span style="color:var(--d)">Earth</span></div>`;
  if (proches.length) {
    ajouter({
      cle: "proches", duree: 9000,
      html: `${tete("Same values", `What <em>matches</em>`)}<div class="corps miroirs">${legendeMiroir}${proches.map((v, i) => ligneMiroir(v, i, false)).join("")}</div>
        <p class="note pied a" style="--i:7">Two bars of the same length: the same place on the variable's scale.${noteRang(proches)}</p>`,
    });
  }
  if (loins.length) {
    ajouter({
      cle: "loins", duree: 9000, classe: "rouge",
      html: `${tete("The gaps", `What <em>differs</em>`)}<div class="corps miroirs">${legendeMiroir}${loins.map((v, i) => ligneMiroir(v, i, true)).join("")}</div>
        <p class="note pied a" style="--i:7">The largest gaps measured between your area and this site.${noteRang(loins)}</p>`,
    });
  }

  // 9. Utile à qui ? (les préréglages du projet appliqués aux ressemblances de ce site)
  if (presets && (presets.presets || []).length && modules.length) {
    const lignes = presets.presets.map((p) => ({ nom: p.name, s: scoreAvec(p.weights) })).filter((p) => p.s != null).sort((a, b) => b.s - a.s);
    if (lignes.length >= 2) {
      ajouter({
        cle: "usages", duree: 9000, classe: "mauve",
        html: `${tete("What it is good for", `Best suited for <em>${echapper(lignes[0].nom)}</em>`)}
          <div class="corps profils">${lignes.map((p, i) => `<div class="profil ${i === 0 ? "top" : ""} a" style="--i:${i + 1}"><span class="nom">${echapper(p.nom)}</span>
            <span class="piste" style="--i:${i}"><i style="--w:${100 * p.s}%"></i></span>${compteur(p.s, "pct", "n")}</div>`).join("")}</div>
          <p class="note pied a" style="--i:7">Similarity of this site with your area ${SUR}, with the criterion weights of each preset in the app.</p>`,
      });
    }
  }

  // 9 bis. Tester sur ce site : l'impact d'une campagne d'essais (mêmes règles que js/analogues.js, impactSite)
  const I = recherche && recherche.pool && recherche.pool.impact;
  const iP = I ? recherche.pool.h3.indexOf(cellule) : -1;
  if (iP >= 0) {
    const val = (x) => (x && x[iP] != null ? x[iP] : null);
    const p = val(I.protected), st = val(I.strict), mi = val(I.mines), ae = val(I.airport_km);
    const cartesI = [];
    if (p != null) {
      const fort = (st ?? 0) >= 0.2 || p >= 0.5, faible = !fort && p < 0.1 && (mi ?? 0) >= 0.005;
      cartesI.push({ t: fort ? "site" : "corps", etq: "Impact", g: fort ? "Protected area" : faible ? "Low impact" : "Medium impact",
        p: fort ? "Mostly in a protected area: tests would need permits and disturb a preserved environment."
          : faible ? "Outside protected areas, on land already transformed by mining."
          : p >= 0.1 ? "Partly in protected areas." : "Outside protected areas, but on land that nothing has transformed yet." });
      cartesI.push({ t: "donnee", etq: "Protected areas", g: pct.format(p), p: `of the site${st >= 0.01 ? `, ${pct.format(st)} strictly protected (national parks, strict reserves)` : ""}.` });
    }
    if (mi != null && mi >= 0.005) cartesI.push({ t: "corps", etq: "Already transformed", g: `${mi < 0.01 ? nb1.format(100 * mi) : nb.format(100 * mi)}%`, p: "of the land is mined: a test adds little to it." });
    const aero = fait("Field campaign", "Nearest airport");
    if (ae != null) cartesI.push({ t: "donnee", etq: "Access", g: `${nb.format(ae)} km`, p: aero ? `to ${echapper(aero.value.replace(/, [\d,]+ km$/, ""))}, the nearest airport with scheduled flights.` : "to the nearest airport with scheduled flights." });
    let dep = null;
    try { dep = JSON.parse(localStorage.getItem("analogues-depart") || "null"); } catch (e) { dep = null; }
    if (dep && fiche && Number.isFinite(dep.lat)) {
      const r = Math.PI / 180, h = Math.sin((fiche.lat - dep.lat) * r / 2) ** 2 + Math.cos(dep.lat * r) * Math.cos(fiche.lat * r) * Math.sin((fiche.lon - dep.lon) * r / 2) ** 2;
      const km = 12742 * Math.asin(Math.min(1, Math.sqrt(h))), d = km * 1.08;          // + 8 % de détours (js/analogues.js)
      const t = (2 * d * (d < 3700 ? 0.126 : 0.117)) / 1000;
      cartesI.push(km < 500 ? { t: "corps", etq: "Getting there", g: `${nb.format(km)} km`, p: `from ${echapper(dep.nom)}: reachable by land.` }
        : { t: "site", etq: "Getting there", g: `${t < 0.1 ? "< 0.1" : nb1.format(t)} t CO₂e`, p: `per person, round trip by plane from ${echapper(dep.nom)} (${nb.format(km)} km).` });
    }
    if (cartesI.length) {
      ajouter({
        cle: "impact", duree: 10000, classe: "vert",
        html: `${tete("Testing there", `What a campaign would <em>cost the Earth</em>`)}
          <div class="corps cartes">${cartesI.map((k, i) => `<div class="carte ${k.t} a" style="--i:${i + 1}"><span class="etq">${k.etq}</span><b>${k.g}</b><p>${k.p}</p></div>`).join("")}</div>
          <p class="note pied a" style="--i:${cartesI.length + 2}">${I.source ? (() => { const w = I.source.match(/\(([^)]*)\), Protected Planet: [^,]*, ([^,]+),/) || [];
            return `Protected areas: UNEP-WCMC and IUCN (${w[1] || ""}), Protected Planet, WDPA ${w[2] || ""}, protectedplanet.net. `; })() : ""}Airports: OurAirports. Flights: UK GHG conversion factors 2025.</p>`,
      });
    }
  }

  // 10. Les limites de ce site
  const cartes = [];
  const veg = fait("Ground", "Dense vegetation"), urb = fait("Ground", "Urban areas"), mine = fait("Caves and volcanoes", "Mines"), nuage = fait("Climate", "Cloud cover");
  if (veg && veg.value >= 5) cartes.push({ t: "site", etq: "On this site", g: `${nb.format(veg.value)}%`, p: "dense vegetation: it hides the ground we want to compare." });
  if (urb && urb.value >= 1) cartes.push({ t: "site", etq: "On this site", g: `${nb1.format(urb.value)}%`, p: "urban areas in the cell." });
  if (mine && mine.value > 0) cartes.push({ t: "site", etq: "On this site", g: `${nb1.format(mine.value)}%`, p: "of the cell covered by mines." });
  if (nuage && nuage.value >= 50) cartes.push({ t: "site", etq: "On this site", g: `${nb.format(nuage.value)}%`, p: "average cloud cover." });
  modules.filter((m) => m.reliability != null && m.reliability < 0.9).forEach((m) =>
    cartes.push({ t: "donnee", etq: "In the data", g: `${nb.format(100 * m.reliability)}%`, p: `data reliability for “${NOMS_SIMPLES[m.key] || m.name}” on this site.` }));
  compositions.filter((v) => !v.compared).forEach((v) =>
    cartes.push({ t: "donnee", etq: "In the data", g: "Not comparable", p: `${nomVar(v).replace(/^./, (x) => x.toUpperCase())}: not all the classes of ${NOMS[corps] === "Moon" ? "the Moon" : NOMS[corps]} are in the Earth data.` }));
  const sansDonnee = Object.keys(NOMS_SIMPLES).filter((k) => !modules.some((m) => m.key === k));
  if (sansDonnee.length) cartes.push({ t: "donnee", etq: "In the data", g: "Not compared", p: `${sansDonnee.map((k) => NOMS_SIMPLES[k]).join(", ")}: no data for your area ${SUR} or for this site.` });
  const phy = PHYSIQUE[corps];
  cartes.push({ t: "corps", etq: "Earth cannot reproduce it", g: `<span class="deux"><span class="g">${nb2.format(phy.g)}</span><span class="d">${nb2.format(PHYSIQUE.earth.g)}</span></span>`,
    p: `Gravity in m/s²: ${NOMS[corps] === "Moon" ? "the Moon" : NOMS[corps]} on the left, Earth on the right.` });
  cartes.push({ t: "corps", etq: "Earth cannot reproduce it", g: `<span class="deux"><span class="g">${phy.pression}</span><span class="d">${PHYSIQUE.earth.pression}</span></span>`,
    p: phy.ptexte });
  ajouter({
    cle: "limites", duree: 11000,
    html: `${tete("Let's be honest", `The <em>limits</em> of this site`)}
      <div class="corps cartes">${cartes.map((k, i) => `<div class="carte ${k.t} a" style="--i:${i + 1}"><span class="etq">${k.etq}</span><b>${k.g}</b><p>${k.p}</p></div>`).join("")}</div>
      <p class="note pied a" style="--i:${cartes.length + 2}">An analog reproduces what can be measured (terrain, rocks, temperature…); it does not replace ${corps === "moon" ? "the Moon" : "Mars"} for what cannot be moved.</p>`,
  });

  // 11. Fin
  ajouter({
    cle: "fin", duree: 0,
    html: `<div class="tete"><p class="kicker a" style="--i:0">In short</p></div>
      <div class="corps fin"><p class="kicker a" style="--i:1">${echapper(lieu)} looks like your area ${SUR}</p>
        ${score != null ? `${compteur(score, "pct", "score a")}<h2 class="a" style="--i:3">${motNiveau(score)}</h2>` : ""}
        <p class="note a" style="--i:4">${rangTexte ? `Site ${rangTexte[0]} of ${rangTexte[1]} · ` : ""}${echapper(sousTitre)}</p>
        <div class="actions a" style="--i:5"><button type="button" id="b-rejouer">↺ Replay</button><button type="button" id="b-lien">Copy the link</button><button type="button" id="b-retour">Back to the map</button></div></div>
      <p class="note pied a" style="--i:6">Source of the values: preprocessing modules (Earth, ${NOMS[corps] === "Moon" ? "the Moon" : NOMS[corps]}), analog server. Place names: Natural Earth, © OpenStreetMap contributors.</p>`,
  });

  // ------------------------------------------------------------------ mise en page et navigation
  document.getElementById("b-attente").remove();
  scene.innerHTML = diapos.map((d, i) => `<section class="s ${d.classe || ""}" data-i="${i}" aria-label="Slide ${i + 1} of ${diapos.length}">${d.html}</section>`).join("");
  const sections = [...scene.querySelectorAll(".s")];
  const progres = document.getElementById("b-progres");
  progres.innerHTML = diapos.map((_, i) => `<button type="button" class="b-seg" data-i="${i}" aria-label="Go to slide ${i + 1}"><i></i></button>`).join("");
  const segs = [...progres.querySelectorAll(".b-seg")];
  const reduit = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let courante = -1;
  let minuteur = null;
  const btnPrec = document.getElementById("b-prec"), btnSuiv = document.getElementById("b-suiv"), btnPause = document.getElementById("b-pause");

  function compter(el) {
    const cible = +el.dataset.n, f = el.dataset.f;
    if (reduit) { el.textContent = formater(cible, f); return; }
    const t0 = performance.now(), duree = 1300;
    const pas = (t) => {
      const k = Math.min(1, (t - t0) / duree);
      el.textContent = formater(cible * (1 - (1 - k) ** 3), f);
      if (k < 1 && el.isConnected && el.closest(".s.on")) requestAnimationFrame(pas);
      else el.textContent = formater(cible, f);
    };
    el.textContent = formater(0, f);
    requestAnimationFrame(pas);
  }

  function aller(i) {
    if (i < 0 || i >= diapos.length || i === courante) return;
    if (courante >= 0) { sections[courante].classList.remove("on"); if (diapos[courante].trois) arreter3D(); }
    courante = i;
    const s = sections[i];
    // redémarre les animations d'entrée : l'élément est retiré puis remis dans le flux
    s.classList.remove("on");
    void s.offsetWidth;
    s.classList.add("on");
    s.querySelectorAll("[data-n]").forEach(compter);
    segs.forEach((g, k) => {
      g.classList.toggle("fait", k < i);
      g.classList.remove("cours");
      g.style.removeProperty("--duree");
    });
    if (diapos[i].duree) {
      void segs[i].offsetWidth;
      segs[i].style.setProperty("--duree", `${diapos[i].duree}ms`);
      segs[i].classList.add("cours");
    }
    btnPrec.disabled = i === 0;
    btnSuiv.disabled = i === diapos.length - 1;
    if (diapos[i].trois) monter3D(s);
    if (diapos[i].cle === "fin") brancherFin(s);
  }
  const suivant = () => aller(courante + 1);
  const precedent = () => aller(courante - 1);

  progres.addEventListener("animationend", (e) => { if (e.animationName === "remplir" && !racine.classList.contains("pause")) suivant(); });
  progres.addEventListener("click", (e) => { const b = e.target.closest(".b-seg"); if (b) aller(+b.dataset.i); });
  btnPrec.addEventListener("click", precedent);
  btnSuiv.addEventListener("click", suivant);
  btnPause.addEventListener("click", () => {
    const p = racine.classList.toggle("pause");
    btnPause.setAttribute("aria-pressed", String(p));
    btnPause.textContent = p ? "▶" : "❚❚";
  });
  scene.addEventListener("click", (e) => {
    if (e.target.closest("canvas,button,a,input,figure")) return;
    if (e.clientX < innerWidth * 0.3) precedent(); else suivant();
  });
  function fermer() {
    if (window.opener && !window.opener.closed) { window.close(); return; }
    location.href = `index.html#${corps}${/^[0-9a-f]{12}$/.test(zoneIdBrut || "") ? "/" + zoneIdBrut : ""}`;
  }
  document.getElementById("b-fermer").addEventListener("click", fermer);
  window.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight" || e.key === " " || e.key === "Enter") { e.preventDefault(); suivant(); }
    else if (e.key === "ArrowLeft") precedent();
    else if (e.key === "p" || e.key === "P") btnPause.click();
    else if (e.key === "Escape") fermer();
  });

  function brancherFin(s) {
    const un = (id, f) => { const b = s.querySelector(id); if (b && !b.dataset.ok) { b.dataset.ok = "1"; b.addEventListener("click", f); } };
    un("#b-rejouer", () => aller(0));
    un("#b-retour", fermer);
    un("#b-lien", async (e) => {
      const b = e.currentTarget;
      try { await navigator.clipboard.writeText(location.href); b.textContent = "Link copied ✓"; } catch (err) { b.textContent = "Could not copy"; }
    });
  }

  // ------------------------------------------------------------------ relief en 3D (three.js)
  let V3 = null;
  function charger(src) {
    return new Promise((ok, ko) => { const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = () => ko(new Error(src)); document.head.appendChild(s); });
  }
  async function monter3D(section) {
    if (V3 && V3.section === section) { V3.stop = false; boucle(); return; }
    const etat = { section, stop: false, cotes: [], leader: 0, auto: true };
    V3 = etat;
    try {
      // node_modules (npm install), sinon unpkg
      if (!window.THREE) await charger("node_modules/three/build/three.min.js").catch(() => charger("https://unpkg.com/three@0.147.0/build/three.min.js"));
      if (!window.THREE.OrbitControls) await charger("node_modules/three/examples/js/controls/OrbitControls.js")
        .catch(() => charger("https://unpkg.com/three@0.147.0/examples/js/controls/OrbitControls.js"));
    } catch (e) {
      section.querySelectorAll(".vide").forEach((p) => { p.textContent = "The 3D library (three.js) could not be loaded: check the Internet connection."; });
      return;
    }
    const donnees = await Promise.all(relief3D.cote);
    if (V3 !== etat) return;
    const ok = donnees.filter((d) => !(d instanceof Error));
    const r = Math.max(0.02, ...ok.map((d) => (d.relief_p5_p95 || 0) / 1000));
    const exag = Math.max(1, Math.min(20, Math.round(cadre.taille / 12 / r)));
    donnees.forEach((d, i) => {
      const cont = section.querySelector(`#b3-${i}`);
      if (d instanceof Error) { cont.innerHTML = `<p class="vide">Terrain unavailable: ${echapper(d.message)}</p>`; return; }
      etat.cotes[i] = construire3D(cont, d, exag, i);
        section.querySelector(`#b3s-${i}`).innerHTML = `<b data-n="${d.relief_p5_p95}" data-f="m">${nb.format(d.relief_p5_p95)} m</b><span>typical elevation range · elevations ${nb.format(d.min)} to ${nb.format(d.max)} m · ×${exag}</span>`;
    });
    boucle();
  }
  function arreter3D() { if (V3) V3.stop = true; }

  function construire3D(cont, d, exag, i) {
    const T = window.THREE, L = cadre.taille, n = d.n;
    cont.innerHTML = "";
    const renderer = new T.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.outputEncoding = T.sRGBEncoding;
    cont.appendChild(renderer.domElement);
    const sc = new T.Scene();
    const camera = new T.PerspectiveCamera(38, 1, L / 200, L * 20);
    sc.add(new T.HemisphereLight(0xffffff, 0x3a3a46, 0.55));
    const soleil = new T.DirectionalLight(0xffffff, 0.95);
    soleil.position.set(-L, L * 0.9, -L * 0.6);
    sc.add(soleil);
    const brutB = Uint8Array.from(atob(d.heights_i16), (ch) => ch.charCodeAt(0));
    const h16 = new Int16Array(brutB.buffer);
    const tri = Float32Array.from(h16).sort();
    const base = tri[Math.floor(tri.length / 2)];
    const geo = new T.PlaneGeometry(L, L, n - 1, n - 1);
    geo.rotateX(-Math.PI / 2);
    const pos = geo.attributes.position;
    const hk = new Float32Array(n * n);
    let min = Infinity;
    for (let k = 0; k < n * n; k++) { hk[k] = ((h16[k] - base) / 1000) * exag; pos.setY(k, hk[k]); min = Math.min(min, hk[k]); }
    geo.computeVertexNormals();
    const bas = tri[Math.floor(tri.length * 0.02)], haut = tri[Math.floor(tri.length * 0.98)];
    const couleurs = new Float32Array(n * n * 3);
    h16.forEach((v, k) => {
      const t = Math.max(0, Math.min(1, (v - bas) / Math.max(1, haut - bas)));
      couleurs[k * 3] = (0.20 + 0.62 * t) ** 2.2; couleurs[k * 3 + 1] = (0.17 + 0.50 * t) ** 2.2; couleurs[k * 3 + 2] = (0.15 + 0.36 * t) ** 2.2;
    });
    geo.setAttribute("color", new T.BufferAttribute(couleurs, 3));
    const materiau = new T.MeshStandardMaterial({ roughness: 1, metalness: 0, vertexColors: true });
    const mesh = new T.Mesh(geo, materiau);
    sc.add(mesh);
    // socle : quatre parois sous les bords, pour l'effet maquette
    const fond = min - L * 0.05;
    const bord = [];
    const pousse = (a, b) => { bord.push(a[0], a[1], a[2], b[0], b[1], b[2], b[0], fond, b[2], a[0], a[1], a[2], b[0], fond, b[2], a[0], fond, a[2]); };
    const P = (k) => [pos.getX(k), pos.getY(k), pos.getZ(k)];
    for (let k = 0; k < n - 1; k++) {
      pousse(P(k), P(k + 1)); pousse(P(n * (n - 1) + k + 1), P(n * (n - 1) + k));
      pousse(P((k + 1) * n), P(k * n)); pousse(P(k * n + n - 1), P((k + 1) * n + n - 1));
    }
    const gs = new T.BufferGeometry();
    gs.setAttribute("position", new T.Float32BufferAttribute(bord, 3));
    sc.add(new T.Mesh(gs, new T.MeshBasicMaterial({ color: new T.Color(0x263042).convertSRGBToLinear(), side: T.DoubleSide })));
    if (d.texture) {
      new T.TextureLoader().load(d.texture, (tex) => {
        tex.encoding = T.sRGBEncoding; tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
        materiau.map = tex; materiau.vertexColors = false; materiau.needsUpdate = true;
      });
    }
    const k = 1.15;
    camera.position.set(L * 0.8 * k, L * 0.7 * k, L * 1.0 * k);
    const controles = new T.OrbitControls(camera, renderer.domElement);
    controles.enableDamping = true; controles.dampingFactor = 0.08; controles.autoRotate = true; controles.autoRotateSpeed = 1.2;
    controles.target.set(0, 0, 0); controles.maxPolarAngle = Math.PI * 0.49;
    controles.addEventListener("start", () => { V3.leader = i; V3.auto = false; });
    const c = { renderer, sc, camera, controles, cont };
    dimensionner(c);
    return c;
  }
  function dimensionner(c) {
    const w = c.cont.clientWidth, h = c.cont.clientHeight;
    if (!w || !h) return;
    c.renderer.setSize(w, h, false);
    c.camera.aspect = w / h;
    c.camera.updateProjectionMatrix();
  }
  function boucle() {
    const etat = V3;
    const f = () => {
      if (!etat || etat.stop || V3 !== etat) return;
      const cotes = etat.cotes.filter(Boolean);
      const chef = etat.cotes[etat.leader] || cotes[0];
      if (chef) {
        chef.controles.autoRotate = etat.auto && !reduit;
        chef.controles.update();
        cotes.forEach((c) => {
          if (c !== chef) { c.camera.position.copy(chef.camera.position); c.camera.quaternion.copy(chef.camera.quaternion); }
          dimensionner(c);
          c.renderer.render(c.sc, c.camera);
        });
      }
      requestAnimationFrame(f);
    };
    requestAnimationFrame(f);
  }
  window.addEventListener("resize", () => { if (V3) V3.cotes.forEach((c) => c && dimensionner(c)); });

  aller(0);
})();
