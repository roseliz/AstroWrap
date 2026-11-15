// Earth analogs: sends the painted area on Mars or the Moon to the server (application/server) and shows
// the most similar sites on the terrestrial globe.
//
// Opened by selection-zone.js with index.html#mars/<id>: the area is saved on the server
// (POST /api/zones) and re-read here (GET /api/zones/<id>); the address never carries H3 cells.
// Without an identifier (#mars alone), the area comes from localStorage ("analogues-zone-mars").
// Server: http://127.0.0.1:8000 by default, or ?api=http://other:port in the address.
//
// Three stages, designed for someone unfamiliar with the data:
// 1. Loading: POST /api/search (1 to 3 s), an indicator in the right panel, then the ranking.
//    (The funnel is no longer replayed step by step: too slow. Its steps remain in the response, for bilan.html.)
// 2. The result, on the right: the list of sites, with a colored word. The "Priority" menu and advanced
//    settings recalculate in the browser (the server sends the similarity of each criterion for ~20,000
//    cells).
// 2 bis. Known analogs (below the list): sites that literature compares to Mars or the Moon, at their actual rank
//    for this area, scored like other sites (same weights, filters, funnel); never added to the ranking.
//    The server sends their similarities with the search (R.known); global check: GET /api/validation.
// 2 ter. "Test responsibly" (below known analogs): the impact of a campaign on each site
//    (WDPA protected areas, mines, airport distance; server: services/impact.py), the best low-impact site,
//    and the flight from the departure city (js/villes.js) with its CO₂; checkbox to exclude protected areas.
// 3. A site's details card, on the left: "Why this site?" in sentences, then the Mars ⟷ Earth criteria, and the
//    side-by-side 3D view button (js/vue-3d.js);
//    POST /api/search/detail (variable-by-variable values) and GET /api/site/{cell} (name, card).
// Depends on MapLibre (window.carteTerre, created by globe-terre.js) and h3-js (window.h3).

(async function () {
  // Serveur : local (http://127.0.0.1:8000) sur cette machine ou en file://, https://api.astrowrap.earth en ligne ; ?api=... l'emporte.
  const API = (new URLSearchParams(location.search).get("api") || (/^(localhost|127\.0\.0\.1|\[::1\]|)$/.test(location.hostname) ? "http://127.0.0.1:8000" : "https://api.astrowrap.earth")).replace(/\/$/, "");
  const H = window.h3;
  const NOMS = { mars: "Mars", moon: "the Moon" };
  const PAGES = { mars: "mars.html", moon: "lune.html" };
  const N_CANDIDATS = 10;
  // Diversité : deux sites de la liste sont au moins à cette distance. 800 km par défaut : sur Gale, Shackleton, les
  // plaines du nord de Mars et Tranquillitatis, la liste couvre plusieurs continents pour un point de ressemblance
  // perdu au 10e site ; 300 km laisse cinq sites dans l'ouest de la Chine pour Gale.
  const ECARTS_KM = [{ km: 300, nom: "Close together" }, { km: 800, nom: "Spread out" }, { km: 1500, nom: "Worldwide" }];
  const CLE_ECART = "analogues-ecart-km";
  let ecartKm = (() => { try { const v = +localStorage.getItem(CLE_ECART); return ECARTS_KM.some((e) => e.km === v) ? v : 800; } catch (e) { return 800; } })();
  const VEGETATION_MAX = 0.3;
  const PROTEGE_MAX = 0.3;            // « Écarter les aires protégées » : plus de 30 % de la cellule en aire protégée
  // Impact d'une campagne d'essais : un niveau, sa couleur et ce qu'il veut dire (impactSite décide)
  const IMPACT = {
    bas: { cle: "faible", nom: "Low impact", texte: "outside protected areas, on land already transformed by mining" },
    moyen: { cle: "moyen", nom: "Medium impact", texte: "partly protected, or land that nothing has transformed yet" },
    haut: { cle: "protege", nom: "Protected area", texte: "mostly in a protected area: tests would need permits and disturb a preserved environment" },
  };
  // Green mode ("responsible testing"): the 10 sites become "similar enough, lowest impact". Kept: at least
  // `plancher` × the similarity of the best site, outside protected areas, and under the CO₂ budget of the flight
  // from the departure city if there is one; ranked by impact (CO₂ of the flight, otherwise distance to the airport;
  // ground already transformed by mines comes slightly ahead), similarity breaking the ties.
  const VERT = { protegeMax: 0.1, strictMax: 0.01, cle: "astrowrap-vert", cleReglages: "astrowrap-vert-reglages",
    planchers: [0.8, 0.9, 0.95], budgets: [null, 0.5, 1, 2], equipe: 5 };
  const MINES_MIN = 0.005;            // 0,5 % de la surface en mines : le terrain est déjà transformé
  // Avion : facteurs de conversion du gouvernement britannique 2025 (DESNZ, Greenhouse gas reporting: conversion factors),
  // classe économique, effets hors CO₂ compris : 0,126 kg CO₂e par passager-km en court-courrier, 0,117 au-delà de
  // 3 700 km ; distance à vol d'oiseau + 8 % pour les détours (méthode du gouvernement britannique) ; aller-retour.
  const VOL = { court: 0.126, long: 0.117, seuilKm: 3700, detour: 1.08, terreKm: 500 };
  const CLE_DEPART = "analogues-depart";
  const VILLES = window.VILLES || [];
  const pct = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 0 });
  const nb = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  const nb1 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
  const nb2 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

  // Niveaux de correspondance : un mot et une couleur par seuil, partout.
  const NIVEAUX = [
    { min: 0.8, nom: "Very close", couleur: "#3DDC97" },
    { min: 0.6, nom: "Close", couleur: "#B9E05A" },
    { min: 0.4, nom: "Partial", couleur: "#F2C14E" },
    { min: -1, nom: "Far", couleur: "#F2545B" },
  ];
  const INCONNU = { nom: "No data", couleur: "#6B7A90" };
  const niveau = (s) => (s == null || Number.isNaN(s) ? INCONNU : NIVEAUX.find((n) => s >= n.min));
  const NOMS_SIMPLES = { thermal: "Temperature", topography: "Terrain", geology: "Rocks", wind: "Wind and dust",
    volatiles: "Ice and water", astro: "Volcanoes and caves" };
  // Variables mises en avant (deux par critère) et leur nom court ; les autres restent dans « En savoir plus ».
  const VEDETTES = { thermal: ["lst_day_mean", "lst_night_mean"], topography: ["part_pente_inf_5", "slopes"],
    geology: ["lithology"], wind: ["part_sol_nu", "part_dunes"], volatiles: ["indice_glace_sol", "part_glace_surface"],
    astro: ["volcanoes", "caves"] };
  const COURTS = { lst_day_mean: "ground temperature by day", lst_night_mean: "ground temperature at night",
    part_pente_inf_5: "flat ground", slopes: "typical slope", lithology: "rocks", mineraux: "minerals",
    part_sol_nu: "bare ground", part_dunes: "dunes", indice_glace_sol: "ground ice", part_glace_surface: "surface ice",
    volcanoes: "volcanoes", caves: "caves and pits", amplitude: "day-night range", part_oxyde_fer: "iron oxides" };
  const COULEUR_CORPS = { mars: "#E0794F", moon: "#C9CED6" };
  const COULEUR_TERRE = "#4FD1FF";
  const CLASSES = { sedimentaire_clastique: "sedimentary", non_consolide: "loose sediments", volcanique_felsique: "felsic volcanic",
    plutonique_basique: "gabbro", plutonique_felsique: "granite", metamorphique: "metamorphic", evaporite: "evaporites",
    argile_al: "Al clays", argile_fe_mg: "Fe-Mg clays", silice_hydratee: "hydrated silica", mafique_autre: "other mafics",
    autre_mineral: "other", pyroxene: "pyroxene", feldspath: "plagioclase", basalte: "basalt", glace: "ice", impact: "impact breccias",
    carbonate: "carbonates", sulfate: "sulfates", sel: "salts", mica: "micas", olivine: "olivine", pyroclastique: "pyroclastic" };
  // Une couleur fixe par classe de roche ou de minéral : la même à gauche et à droite.
  const COULEUR_CLASSE = { basalte: "#5B6C8F", volcanique_felsique: "#C9A0DC", pyroclastique: "#E07A5F", plutonique_basique: "#3D5A80",
    plutonique_felsique: "#F4A6A6", sedimentaire_clastique: "#E9C46A", non_consolide: "#F4E3B1", carbonate: "#A8DADC",
    evaporite: "#FFFFFF", metamorphique: "#8D99AE", glace: "#BDE0FE", impact: "#6D597A", pyroxene: "#2A9D8F", olivine: "#8AB17D",
    feldspath: "#E5E5E5", mafique_autre: "#52796F", argile_al: "#DDB892", argile_fe_mg: "#B08968", mica: "#CDB4DB",
    sulfate: "#FFD166", silice_hydratee: "#90E0EF", sel: "#F8F9FA", autre_mineral: "#ADB5BD" };

  /** A readable value: °C, %, level within the body, dominant rock… */
  // Level of a value within its body: below 20% of the cells "very low", etc.
  const NIVEAUX_RANG = [[0.2, "very low"], [0.4, "low"], [0.6, "average"], [0.8, "high"], [Infinity, "very high"]];
  function lisible(v, meta, cote) {
    if (v == null) return "–";
    if (meta.mode === "hellinger") {
      const top = Object.entries(v).filter(([, x]) => x != null && x >= 0.05).sort((a, b) => b[1] - a[1]).slice(0, 2);
      return top.length ? top.map(([k, x]) => `${CLASSES[k] || k.replace(/_/g, " ")} ${pct.format(x)}`).join(", ") : "no dominant type";
    }
    if (meta.mode === "deciles") return `${nb1.format(v[Math.floor(v.length / 2)] ?? 0)}°`;
    if (meta.mode === "rank" || /_rang$/.test(meta.key)) {
      // Rank within the body (0 to 1): a level in words ("high" for Mars), and the real value when the server gives it
      const mot = NIVEAUX_RANG.find(([s]) => v < s)[1];
      const reel = cote && meta[`${cote}_value`];
      if (reel == null) return mot.replace(/^./, (x) => x.toUpperCase());
      const u = (meta.value_unit || "").replace(/^per /, "/");
      const t = Math.abs(reel) >= 100 ? nb.format(reel) : Math.abs(reel) >= 10 ? nb1.format(reel) : nb2.format(reel);
      return `${t}${u.startsWith("×") ? u : " " + u} (${mot})`;
    }
    if (meta.unit === "K") return meta.key === "amplitude" ? `${nb.format(v)} °C` : `${nb.format(v - 273.15)} °C`;
    if (meta.unit === "°") return `${nb1.format(v)}°`;
    if (!meta.unit && v >= 0 && v <= 1) return pct.format(v);
    return `${nb2.format(v)}${meta.unit ? " " + meta.unit : ""}`;
  }
  const echapper = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const mot = (s) => { const n = niveau(s); return `<span class="mot" style="--c:${n.couleur}">${n.nom}</span>`; };
  /** Le pourcentage de ressemblance dans une pastille de la couleur de son niveau (le mot au survol). */
  const pastille = (s) => { const n = niveau(s); return `<span class="mot" style="--c:${n.couleur}" title="${n.nom}">${pct.format(s)}</span>`; };

  // #mars/<id> (zone enregistrée sur le serveur), #mars (zone dans localStorage) ; les anciennes adresses
  // #corps=mars&zone=... restent lues, puis la zone quitte l'adresse.
  const params = new URLSearchParams(location.hash.slice(1));
  const [brut, ident] = (params.get("corps") || location.hash.slice(1).split("&")[0]).split("/");
  const corps = { lune: "moon" }[brut] || (["mars", "moon"].includes(brut) ? brut : "");
  const CLE_ZONE = `analogues-zone-${corps}`;
  let texteZone = params.get("zone") || "";
  let zoneId = /^[0-9a-f]{12}$/.test(ident || "") ? ident : "";
  if (corps && zoneId && !texteZone) {
    try {
      const r = await fetch(`${API}/api/zones/${zoneId}`);
      if (r.ok) texteZone = ((await r.json()).h3_cells || []).join(",");
    } catch (e) { /* serveur injoignable : on essaie le navigateur, la recherche dira l'erreur */ }
  }
  if (texteZone && !zoneId) {
    try { localStorage.setItem(CLE_ZONE, texteZone); } catch (e) { /* on garde la zone de l'adresse */ }
  } else if (corps && !texteZone) {
    try { texteZone = localStorage.getItem(CLE_ZONE) || ""; } catch (e) { texteZone = ""; }
  }
  if (corps) history.replaceState(null, "", `${location.pathname}${location.search}#${corps}${zoneId ? "/" + zoneId : ""}`);
  // Une autre zone dans l'adresse (lien « Terre » de la barre de navigation, ou adresse collée) : la page repart
  // de zéro, plus simple et plus sûr que de tout remettre à zéro ici. history.replaceState ne déclenche pas cet événement.
  window.addEventListener("hashchange", () => location.reload());
  const zone = texteZone.split(",").filter(Boolean);
  // La barre de navigation (js/navigation.js) ramène à cette zone depuis les autres pages (lien « Terre »)
  if (corps && zoneId && zone.length && window.navigation) window.navigation.memoriser({ body: corps, id: zoneId });
  const SUR = NOMS[corps] ? `on ${NOMS[corps]}` : "";

  // ------------------------------------------------------------------ panneau de droite
  const panneau = document.createElement("aside");
  panneau.className = "analogues";
  document.body.appendChild(panneau);
  const $ = (s) => panneau.querySelector(s);

  if (!corps || !zone.length) {
    panneau.innerHTML = `
      <h2>Find an analog</h2>
      ${corps ? `<p class="analogues-erreur">The area ${SUR} could not be found (the server was restarted, or another
      browser). Go back and paint it on <a href="${PAGES[corps]}${location.search}">${NOMS[corps]}</a>.</p>` : ""}
      <p>Paint an area on <a href="mars.html">Mars</a> or on <a href="lune.html">the Moon</a>, then
      choose “Compare with Earth”.</p>
      <p class="analogues-etat" id="an-etat">Server: checking…</p>`;
    fetch(`${API}/api/health`).then((r) => r.json())
      .then((d) => { $("#an-etat").textContent = d.earth.ready ? `Server ready (${API}).` : "Server started, loading the Earth data…"; })
      .catch(() => { $("#an-etat").innerHTML = messageServeur(); });
    // Accueil : le choix de l'astre, au centre (js/accueil.js) ; le panneau permet de le rouvrir
    // #terre (lien « Terre » de la barre de navigation) : le globe à explorer, sans la fenêtre d'accueil
    if (!corps && window.accueil && location.hash !== "#terre") {
      panneau.insertAdjacentHTML("beforeend", `<button type="button" class="analogues-rejouer" id="an-accueil">Choose a body</button>`);
      $("#an-accueil").addEventListener("click", () => window.accueil.ouvrir());
      window.accueil.ouvrir();
    }
    return;
  }
  if (!H || !window.maplibregl || !window.carteTerre || !window.carteTerre.addSource) {
    panneau.innerHTML = `<h2>Analogs</h2><p class="analogues-erreur">The 3D globe or h3-js could not start: the
      results cannot be shown in this browser.</p>`;
    return;
  }
  const map = window.carteTerre;
  if (window.arreterRotationTerre) window.arreterRotationTerre();
  const sousTitre = document.querySelector(".titre p");
  if (sousTitre) sousTitre.hidden = true;               // the title of the right panel says the same

  panneau.innerHTML = `
    <div class="analogues-tete">
      <div class="analogues-titre-ligne"><h2 id="an-titre">Searching…</h2>
        <button type="button" class="replier" id="an-replier" aria-expanded="true" aria-label="Collapse the results panel" title="Collapse"><svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 10l4-4 4 4"/></svg></button></div>
      <a class="analogues-retour" href="${PAGES[corps] || "index.html"}${location.search}${zoneId ? "#" + zoneId : ""}">← Edit the area ${SUR}</a>
      <button type="button" class="vert-bascule" id="an-vert" role="switch" aria-checked="false" hidden>
        <span class="vert-piste" aria-hidden="true"><i></i></span><span>Green mode</span></button>
      <p class="vert-bilan" id="an-vert-bilan" hidden></p>
    </div>
    <p class="analogues-etat" id="an-etat" hidden></p>
    <div class="analogues-chargement" id="an-chargement" role="status" hidden>
      <span class="analogues-roue" aria-hidden="true"></span>
      <span>Comparing your area with the whole Earth…</span>
    </div>
    <div class="an-onglets" role="tablist" aria-label="Results">
      <button type="button" role="tab" id="an-onglet-sites" aria-selected="true" aria-controls="an-vue-sites">Sites</button>
      <button type="button" role="tab" id="an-onglet-impact" aria-selected="false" aria-controls="an-vue-impact" tabindex="-1">Responsible testing</button>
    </div>
    <div class="an-vue" id="an-vue-impact" role="tabpanel" aria-labelledby="an-onglet-impact" hidden>
    <section class="impact" id="an-impact">
      <div class="impact-depart">
        <label for="an-depart">Your departure city</label>
        <div class="impact-depart-ligne">
          <input type="text" id="an-depart" list="an-villes" placeholder="Type a city, e.g. Montréal" autocomplete="off" spellcheck="false">
          <button type="button" id="an-ici" class="impact-ici" aria-label="Use my location" title="Use my location">
            <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="8" cy="8" r="4.5"/><path d="M8 1v2.5M8 12.5V15M1 8h2.5M12.5 8H15"/></svg>
          </button>
        </div>
        <datalist id="an-villes"></datalist>
      </div>
      <div class="vert-reglages" id="an-vert-reglages" hidden></div>
      <div class="impact-cartes" id="an-impact-cartes"></div>
      <p class="impact-sources" id="an-impact-sources"></p>
    </section>
    </div>
    <div class="an-vue" id="an-vue-sites" role="tabpanel" aria-labelledby="an-onglet-sites">
    <div class="an-ecart" role="group" aria-label="Distance between the sites">
      ${ECARTS_KM.map((e) => `<button type="button" data-km="${e.km}" aria-pressed="${e.km === ecartKm}" title="At least ${nb.format(e.km)} km between two sites">${e.nom}</button>`).join("")}
    </div>
    <ol class="analogues-liste" id="an-liste"></ol>
    <section class="connus" id="an-connus" hidden aria-labelledby="an-connus-titre">
      <h3 id="an-connus-titre" title="Sites that scientists already compare with places ${SUR}, at their real rank for your area">Known analogs</h3>
      <ul class="connus-liste" id="an-connus-liste"></ul>
    </section>
    <section class="analogues-poids" aria-labelledby="an-poids-titre">
      <div class="analogues-poids-tete">
        <h3 id="an-poids-titre">Weight of each criterion</h3>
        <select id="an-preset" aria-label="Weight preset"></select>
      </div>
      <div id="an-poids"></div>
    </section>
    <details class="analogues-avance">
      <summary>Advanced settings</summary>
      <label class="analogues-case"><input type="checkbox" id="an-vegetation" checked>
        Ignore places covered by vegetation (forests, crops)</label>
      <label class="analogues-case" id="an-protegees-case" hidden><input type="checkbox" id="an-protegees">
        Set aside protected areas (national parks, reserves)</label>
    </details>
    <details class="reference" id="an-reference" hidden>
      <summary>Your area ${SUR}</summary>
      <div id="an-reference-corps"></div>
    </details>
    </div>`;

  // Replier le panneau de droite : il ne garde que son titre
  $("#an-replier").addEventListener("click", () => {
    const replie = panneau.classList.toggle("replie");
    $("#an-replier").setAttribute("aria-expanded", String(!replie));
    $("#an-replier").setAttribute("aria-label", replie ? "Expand the results panel" : "Collapse the results panel");
  });

  // Écart entre les sites de la liste : recalcul dans le navigateur, gardé pour les prochaines fois
  panneau.querySelectorAll(".an-ecart button").forEach((b) => b.addEventListener("click", () => {
    ecartKm = +b.dataset.km;
    try { localStorage.setItem(CLE_ECART, String(ecartKm)); } catch (e) { /* private browsing */ }
    panneau.querySelectorAll(".an-ecart button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    recalculer(true);
  }));

  // Onglets du panneau : les sites, ou « tester de façon responsable »
  const onglets = [...panneau.querySelectorAll('.an-onglets [role="tab"]')];
  function ouvrirOnglet(b, focus = false) {
    onglets.forEach((o) => {
      const oui = o === b;
      o.setAttribute("aria-selected", String(oui));
      o.tabIndex = oui ? 0 : -1;
      $(`#${o.getAttribute("aria-controls")}`).hidden = !oui;
    });
    if (focus) b.focus();
  }
  onglets.forEach((b, k) => {
    b.addEventListener("click", () => ouvrirOnglet(b));
    b.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      e.preventDefault();
      ouvrirOnglet(onglets[(k + (e.key === "ArrowRight" ? 1 : onglets.length - 1)) % onglets.length], true);
    });
  });

  let modules = [];               // GET /api/modules (ceux qui ont des données pour ce corps)
  let presets = [];
  // Mission chosen before painting (selection-zone.js): the search starts with its weights (server preset)
  // (only a preset key the server knows: an unknown one would make the search fail)
  const mission = (() => { try { return localStorage.getItem(`astrowrap-mission-${corps}`) || ""; } catch (e) { return ""; } })()
    .replace(/^(?!(balanced|landing|geology|astrobiology|climate)$).*/, "");
  let poids = {};                 // poids bruts
  let R = null;                   // dernière réponse de /api/search
  let classement = null;          // calcul local : { ordre, scores, candidats, connus }
  let marqueurs = [];
  let marqueursConnus = [];

  function messageServeur() {
    return `The server does not respond at ${API}. Start it with <code>npm start</code> in
      <code>application/client</code> (or <code>uvicorn app.main:app</code> in <code>application/server</code>), then reload the page.`;
  }
  /** Message dans le panneau de droite (erreurs surtout) ; vide = masqué. */
  function etat(html, erreur = false) {
    $("#an-etat").innerHTML = html;
    $("#an-etat").hidden = !html;
    $("#an-etat").className = erreur ? "analogues-erreur" : "analogues-etat";
    if (erreur) { chargement(false); if (window.satellites) window.satellites.terminer(); }
  }
  const nomModule = (cle) => NOMS_SIMPLES[cle] || (modules.find((m) => m.key === cle) || { name: cle }).name;

  // ------------------------------------------------------------------ démarrage
  async function demarrer() {
    // La recherche part tout de suite, en même temps que la liste des modules : poids vides = poids par défaut
    // du serveur, les mêmes que les curseurs au départ.
    chargement(true);
    prechargerRelief(null);            // the terrain of the area (slow on the Moon) starts with the search
    const premiere = requete();
    try {
      const [m, p] = await Promise.all([fetch(`${API}/api/modules`).then((r) => r.json()), fetch(`${API}/api/presets`).then((r) => r.json())]);
      modules = m.modules.filter((x) => x.bodies.includes(corps) && x.available[corps] && x.available.earth);
      presets = p.presets;
    } catch (e) {
      etat(messageServeur(), true);
      return;
    }
    const pm = presets.find((p) => p.key === mission);
    modules.forEach((x) => { poids[x.key] = pm ? pm.weights[x.key] ?? x.default_weight : x.default_weight; });
    if (window.satellites) window.satellites.contexte({ poids });     // the window of a satellite reads the weights
    $("#an-preset").innerHTML = presets.map((p) => `<option value="${p.key}">${p.name}</option>`).join("") + `<option value="">Custom</option>`;
    if (pm) $("#an-preset").value = pm.key;
    $("#an-preset").addEventListener("change", () => {
      const p = presets.find((x) => x.key === $("#an-preset").value);
      if (!p) return;
      modules.forEach((x) => { poids[x.key] = p.weights[x.key] ?? x.default_weight; });
      majCurseurs();
      recalculer();
    });
    $("#an-poids").innerHTML = modules.map((x) => `
      <label class="analogues-curseur">
        <span>${nomModule(x.key)}</span>
        <input type="range" min="0" max="3" step="0.5" value="${poids[x.key]}" data-module="${x.key}">
        <output></output>
      </label>`).join("");
    $("#an-poids").querySelectorAll("input").forEach((i) => i.addEventListener("input", () => {
      poids[i.dataset.module] = +i.value;
      $("#an-preset").value = "";
      majCurseurs();
      recalculer();
    }));
    majCurseurs();
    $("#an-vegetation").addEventListener("change", () => chercher());
    panneau.querySelectorAll(".vert-bascule").forEach((b) => b.addEventListener("click", () => {
      modeVert = !modeVert;
      try { sessionStorage.setItem(cleVert, modeVert ? "1" : "0"); } catch (e) { /* private browsing */ }
      appliquerModeVert();
      fermerSite();
      recalculer();
      // the responsible testing tab (settings and gains of green mode) opens; without a departure city, the cursor
      // goes to that field (the CO₂ of the flight ranks the sites)
      ouvrirOnglet($("#an-onglet-impact"));
      if (modeVert && !depart) $("#an-depart").focus();
    }));
    $("#an-protegees").addEventListener("change", () => chercher());
    preparerDepart();
    afficherRecherche(await premiere);
  }

  /** Pourcentages sur les seuls critères utilisables pour cette zone ; les autres sont grisés. */
  function majCurseurs() {
    const utilisables = R ? R.active_modules.concat((R.inactive_modules || []).filter((m) => m.reason === "zero weight").map((m) => m.key))
      : modules.map((m) => m.key);
    const total = utilisables.reduce((a, m) => a + (poids[m] || 0), 0) || 1;
    $("#an-poids").querySelectorAll("input").forEach((i) => {
      const ok = utilisables.includes(i.dataset.module);
      i.value = poids[i.dataset.module];
      i.disabled = !ok;
      i.closest("label").classList.toggle("inactif", !ok);
      i.closest("label").title = ok ? "" : "No data for this area";
      i.nextElementSibling.textContent = ok ? pct.format(poids[i.dataset.module] / total) : "–";
    });
  }

  /** Pendant la recherche : le panneau ne montre que son titre et l'indicateur. */
  let balayage = false;                  // search or scans running: the sites cannot be browsed yet
  function chargement(oui) {
    if (oui) { balayage = true; document.body.classList.add("an-balayage"); }
    else if (balayage && !$("#an-etat").hidden) { balayage = false; document.body.classList.remove("an-balayage"); }
    if (oui && window.satellites) window.satellites.chercher();      // they finish their turn in afficherRecherche
    panneau.classList.toggle("en-chargement", oui);
    $("#an-chargement").hidden = !oui;
    if (oui) $("#an-titre").textContent = "Searching for analogs…";
  }

  /** Nouvelle recherche (filtre de végétation changé) ; les poids, eux, se recalculent dans le navigateur. */
  async function chercher() {
    chargement(true);
    effacerResultats();
    afficherRecherche(await requete());
  }

  /** POST /api/search : la réponse, ou null après avoir affiché l'erreur. */
  async function requete() {
    let r;
    try {
      r = await fetch(`${API}/api/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          body: corps, h3_cells: zone, weights: poids, top_k: 2000,
          ...(mission && !Object.keys(poids).length ? { preset: mission } : {}),
          filters: filtres(),
        }),
      });
      const d = await r.json();
      if (r.ok) return d;
      const detail = Array.isArray(d.detail) ? d.detail.map((x) => x.msg).join(" ; ") : d.detail;
      etat(r.status === 503 ? `The server is not ready: ${detail}` : `The server rejects the area: ${detail}`, true);
    } catch (e) {
      etat(messageServeur(), true);
    }
    return null;
  }

  function filtres() {
    const f = {};
    if ($("#an-vegetation").checked) f.max_vegetation = VEGETATION_MAX;
    if ($("#an-protegees").checked) f.max_protected = PROTEGE_MAX;
    return f;
  }

  /** Une fois par zone, après la première recherche : « Your AstroWrap is ready », qui lance le récap du site 1. */
  function wrapPret() {
    const C = classement, c = C && C.candidats[0];
    const cle = `astrowrap-vu-${corps}-${zoneId || zone.length}`;
    try { if (!c || localStorage.getItem(cle)) return; localStorage.setItem(cle, "1"); } catch (e) { if (!c) return; }
    const el = document.createElement("div");
    el.className = "wrap-pret";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "true");
    el.setAttribute("aria-labelledby", "wrap-pret-titre");
    el.innerHTML = `<div class="wrap-carte" style="--corps:${COULEUR_CORPS[corps]}">
        <img src="images/astrowrap-wordmark.png" alt="AstroWrap" height="34">
        <p class="wrap-sur">Your AstroWrap · ${NOMS[corps].replace(/^the /, "The ")}</p>
        <span class="wrap-astre" aria-hidden="true"></span>
        <h2 id="wrap-pret-titre">${nb.format(R.footprint ? R.footprint.zone_area_km2 : 0)} km² ${SUR}</h2>
        <p class="wrap-texte">compared with <b>${nb.format(R.n_cells_earth)}</b> places on Earth. Your Earth twin:
          <b class="wrap-nom">${echapper(noms[c.h3] || lireCoords(c))}</b>, ${pct.format(c.score)} similar.</p>
        <button type="button" class="wrap-jouer">▶ Play my AstroWrap</button>
        <button type="button" class="wrap-passer">Explore the results</button>
      </div>`;
    document.body.appendChild(el);
    const fermer = () => { el.remove(); document.removeEventListener("keydown", echap, true); };
    const echap = (e) => { if (e.key === "Escape") { e.stopImmediatePropagation(); fermer(); } };
    document.addEventListener("keydown", echap, true);
    el.addEventListener("click", (e) => { if (e.target === el) fermer(); });
    el.querySelector(".wrap-passer").addEventListener("click", fermer);
    el.querySelector(".wrap-jouer").addEventListener("click", () => { ouvrirBilan(c, 1); fermer(); });
    el.querySelector(".wrap-jouer").focus();
    // le nom du site 1 arrive après (POST /api/names) : on le met à jour s'il est encore ouvert
    const t = setInterval(() => {
      if (!el.isConnected) { clearInterval(t); return; }
      if (noms[c.h3]) { el.querySelector(".wrap-nom").textContent = noms[c.h3]; clearInterval(t); }
    }, 300);
  }

  // Relief de la diapositive 3D du bilan (zone + site), demandé dès que les résultats arrivent et à chaque fiche
  // ouverte : le serveur le calcule et le garde pendant qu'on regarde la page, le bilan l'a aussitôt.
  const reliefsDemandes = new Map();     // path -> promise (resolved when the server is done, error included)
  let cadreBilan = null;
  function prechargerRelief(c) {
    const RB = window.reliefBilan;
    if (!RB || !zone.length) return Promise.resolve();
    if (!cadreBilan) { try { cadreBilan = RB.cadre(RB.cellules6(zone), corps); } catch (e) { return Promise.resolve(); } }
    const demandes = [[corps, cadreBilan.lat, cadreBilan.lon]];
    // le bilan ne montre le relief que s'il se ressemble (topographie ≥ 60 %)
    if (c && (c.modules && c.modules.topography != null ? c.modules.topography : 1) >= 0.55) demandes.push(["earth", c.lat, c.lon]);
    return Promise.all(demandes.map(([b, la, lo]) => {
      const ch = RB.chemin(b, la, lo, cadreBilan.taille);
      if (!reliefsDemandes.has(ch)) {
        reliefsDemandes.set(ch, fetch(`${API}${ch}`).then((r) => { if (!r.ok) reliefsDemandes.delete(ch); return r.blob(); })
          .catch(() => { reliefsDemandes.delete(ch); }));
      }
      return reliefsDemandes.get(ch);
    }));
  }

  function afficherRecherche(d) {
    if (!d) return;
    R = d;
    if (window.satellites) window.satellites.contexte({ actifs: R.active_modules });
    $("#an-protegees-case").hidden = !(R.pool.impact && R.pool.impact.protected);
    $("#an-vert").hidden = !(R.pool.impact && R.pool.impact.protected);
    if ($("#an-vert").hidden && modeVert) { modeVert = false; }
    appliquerModeVert();
    if (zoneId && R.footprint && window.navigation) window.navigation.memoriser({ body: corps, id: zoneId, km2: R.footprint.zone_area_km2 });
    etat("");
    majCurseurs();
    afficherReference();
    recalculer(true);
    // The results stay hidden while the satellites scan; "Your AstroWrap is ready" opens right after the last scan,
    // before the sites can be browsed. The 3D terrain of the wrap (area and site 1) keeps being computed behind: the
    // wrap waits for it itself if it is not ready yet.
    prechargerRelief(classement && classement.candidats[0]);
    const titre = $("#an-titre").textContent;
    $("#an-titre").textContent = "Scanning your area with each module…";
    const fini = window.satellites ? window.satellites.terminer() : Promise.resolve();
    Promise.race([fini, new Promise((r) => setTimeout(r, 15000))]).then(() => {
      if (!balayage) return;
      balayage = false;
      document.body.classList.remove("an-balayage");
      chargement(false);
      $("#an-titre").textContent = titre;
      wrapPret();
    });
  }

  /** Ce que la zone de référence est, critère par critère, en clair. */
  function afficherReference() {
    const lignes = R.active_modules.map((cle) => {
      const ref = R.reference[cle];
      const vars = (VEDETTES[cle] || []).map((k) => ref.variables.find((v) => v.key === k)).filter(Boolean);
      const montre = (vars.length ? vars : ref.variables.slice(0, 2))
        .map((v) => `<span>${COURTS[v.key] || v.label}: <b>${lisible(v.value, v)}</b></span>`);
      return `<li><span class="ref-nom">${nomModule(cle)}</span>
        <span class="ref-valeurs">${montre.join("")}</span></li>`;
    });
    $("#an-reference-corps").innerHTML = `<ul class="ref-liste">${lignes.join("")}</ul>`;
    $("#an-reference").hidden = false;
  }

  // ------------------------------------------------------------------ classement local (poids du navigateur)
  function recalculer(afficherAussi = true) {
    if (!R) return;
    const actifs = R.active_modules.filter((m) => (poids[m] ?? 0) > 0);
    if (!actifs.length) { etat("All criteria are set to zero.", true); return; }
    const total = actifs.reduce((a, m) => a + poids[m], 0);
    const w = Object.fromEntries(actifs.map((m) => [m, poids[m] / total]));
    const P = R.pool, n = P.h3.length;
    const eauMax = R.footprint ? R.footprint.max_water : 1;
    const scores = new Float64Array(n).fill(-1);
    const libres = new Float64Array(n).fill(-1);        // sans l'entonnoir : pour situer un analogue connu écarté
    for (let i = 0; i < n; i++) {
      if (P.water_share && P.water_share[i] > eauMax) continue;   // empreinte trop en mer (côtes, îles)
      const r = noterLigne(P, i, actifs, w);
      if (r.mesure < R.confidence_min) continue;
      libres[i] = r.score;
      if (!r.ecarte) scores[i] = r.score;
    }
    const ordre = [...scores.keys()].filter((i) => scores[i] >= 0).sort((a, b) => scores[b] - scores[a]);
    const choisirSites = (liste) => {
      const out = [];
      for (const i of liste) {
        const [la, lo] = H.cellToLatLng(P.h3[i]);
        if (out.every((c) => distanceKm(la, lo, c.lat, c.lon) >= ecartKm)) {
          out.push({ i, h3: P.h3[i], lat: la, lon: lo, score: scores[i], impact: impactSite(P.impact, i),
            modules: Object.fromEntries(actifs.map((m) => [m, P.score_per_module[m][i]])) });
          if (out.length >= N_CANDIDATS) break;
        }
      }
      return out;
    };
    let candidats = choisirSites(ordre), standard = null;
    if (modeVert && P.impact) {
      const I = P.impact, plancher = (ordre.length ? scores[ordre[0]] : 0) * reglagesVert.plancher, gardes = [];
      for (const i of ordre) {
        if (scores[i] < plancher) break;                       // ordre is sorted: the rest is under the floor
        if (exclueProtegee(I, i)) continue;
        const c = coutVert(I, i);
        if (reglagesVert.budget != null && c.co2 != null && c.co2 > reglagesVert.budget) continue;
        gardes.push({ i, cout: c.cout });
      }
      gardes.sort((a, b) => a.cout - b.cout || scores[b.i] - scores[a.i]);
      standard = candidats;
      candidats = choisirSites(gardes.map((x) => x.i));
    }
    classement = { ordre, scores, candidats, standard,
      connus: situerConnus(scores, libres, actifs, w, eauMax) };
    if (afficherAussi) afficher(true);
  }

  /** Score d'une ligne de la réserve (ou d'une cellule d'un analogue connu), comme le serveur : un critère sans
   *  donnée prend la médiane de la Terre ; `ecarte` : le premier critère sous la médiane (l'entonnoir). */
  function noterLigne(L, i, actifs, w) {
    let s = 0, ws = 0, mesure = 0, ecarte = null;
    for (const m of actifs) {
      const sim = L.score_per_module[m][i];
      if (sim == null) { s += R.medians[m] * w[m]; ws += w[m]; continue; }
      if (sim < R.medians[m] && !ecarte) ecarte = m;
      const we = w[m] * (0.5 + 0.5 * (L.reliability_per_module[m][i] ?? 1));
      s += sim * we; ws += we; mesure += w[m];
    }
    return { score: s / ws, mesure, ecarte };
  }

  /** Rang réel de chaque analogue connu (sa cellule ou une voisine, la meilleure) parmi les cellules de la réserve
   *  qui passent les mêmes filtres, sans l'entonnoir (comme GET /api/validation : l'entonnoir garde quelques centaines
   *  de cellules, une part parmi elles ne dirait rien) ; puis s'il passe l'entonnoir, et son rang parmi les restantes. */
  function situerConnus(scores, libres, actifs, w, eauMax) {
    const vegMax = $("#an-vegetation").checked ? VEGETATION_MAX : Infinity;
    const protMax = $("#an-protegees").checked ? PROTEGE_MAX : Infinity;
    const nAvec = scores.reduce((a, x) => a + (x >= 0), 0);
    const nSans = libres.reduce((a, x) => a + (x >= 0), 0);
    const rang = (tab, s) => 1 + tab.reduce((a, x) => a + (x > s), 0);
    return (R.known || []).map((a) => {
      const k = { ...a, cause: a.h3.length ? null : "eau" };
      let avec = null, sans = null, vert = false, sec = false, protege = false;
      a.h3.forEach((h, j) => {
        if (a.water_share[j] != null && a.water_share[j] > eauMax) return;
        sec = true;
        if ((a.vegetation[j] ?? 0) > vegMax) { vert = true; return; }
        if (((a.protected || [])[j] ?? 0) > protMax) { protege = true; return; }
        const r = noterLigne(a, j, actifs, w);
        if (r.mesure < R.confidence_min) return;
        if (!sans || r.score > sans.score) sans = { ...r, j };
        if (!r.ecarte && (!avec || r.score > avec.score)) avec = { ...r, j };
      });
      const choix = avec || sans;
      if (choix) {
        const [lat, lon] = H.cellToLatLng(a.h3[choix.j]);
        Object.assign(k, { cellule: a.h3[choix.j], lat, lon, score: choix.score, impact: impactSite(a.impact, choix.j),
          modules: Object.fromEntries(actifs.map((m) => [m, a.score_per_module[m][choix.j]])) });
      }
      if (sans) Object.assign(k, { rang: rang(libres, sans.score), n: nSans, garde: !!avec, module: sans.ecarte });
      if (avec) Object.assign(k, { rangAvec: rang(scores, avec.score), nAvec });
      if (!sans && !k.cause) k.cause = !sec ? "eau" : vert ? "vegetation" : protege ? "protegee" : "donnees";
      k.part = k.rang ? k.rang / Math.max(k.n, 1) : null;
      return k;
    }).sort((x, y) => ordreConnu(x) - ordreConnu(y));
  }
  const ordreConnu = (k) => (k.scope === "mineralogy" ? 2 : 0) + (k.cause ? 1 : 0) + (k.part ?? 1) * 0.99;

  /** Sur le globe, MapLibre grossit les hautes latitudes à zoom égal : on compense pour garder la même échelle. */
  const zoomA = (z, lat, min) => Math.max(min, z - Math.log2(1 / Math.max(0.05, Math.cos(lat * Math.PI / 180))));

  function distanceKm(la1, lo1, la2, lo2) {
    const r = Math.PI / 180, a = Math.sin((la2 - la1) * r / 2) ** 2 + Math.cos(la1 * r) * Math.cos(la2 * r) * Math.sin((lo2 - lo1) * r / 2) ** 2;
    return 12742 * Math.asin(Math.min(1, Math.sqrt(a)));
  }

  // ------------------------------------------------------------------ carte
  function contour(cellule) {
    const b = H.cellToBoundary(cellule, true);
    const lons = b.map((p) => p[0]);
    if (Math.max(...lons) - Math.min(...lons) > 180) b.forEach((p) => { if (p[0] < 0) p[0] += 360; });
    return b;
  }
  const vide = () => ({ type: "FeatureCollection", features: [] });
  const polygone = (c, props = {}) => ({ type: "Feature", properties: props, geometry: { type: "Polygon", coordinates: [contour(c)] } });
  /** Contour extérieur d'un groupe de cellules (l'empreinte jugée autour d'un site). */
  function contourEmpreinte(cellules) {
    try {
      return H.cellsToMultiPolygon(cellules, true).map((p) => ({ type: "Feature", properties: {},
        geometry: { type: "Polygon", coordinates: p.map((anneau) => {
          const lons = anneau.map((q) => q[0]);
          if (Math.max(...lons) - Math.min(...lons) > 180) anneau.forEach((q) => { if (q[0] < 0) q[0] += 360; });
          return anneau;
        }) } }));
    } catch (e) {
      return cellules.map((c) => polygone(c));
    }
  }

  function couches() {
    if (map.getSource("an-choix")) return;
    ["an-choix"]
      .forEach((id) => map.addSource(id, { type: "geojson", data: vide() }));
    // Les sites retenus sont des repères (losanges numérotés) ; le site ouvert montre la surface exacte sur
    // laquelle il est jugé (son empreinte, de même surface que la zone), remplie et cernée de blanc.
    map.addLayer({ id: "an-choix-fond", type: "fill", source: "an-choix",
      paint: { "fill-color": "#FFFFFF", "fill-opacity": 0.14 } });
    map.addLayer({ id: "an-choix", type: "line", source: "an-choix", paint: { "line-color": "#FFFFFF", "line-width": 2.5 } });
  }
  // "load" fires only once: isStyleLoaded() turns false again while a source loads, and waiting for "load" at
  // that moment would wait forever.
  // So try right away, then at each map event until it works.
  function quandPret(f) {
    const essai = () => { try { f(); return true; } catch (e) { return false; } };
    if (essai()) return;
    const g = () => { if (essai()) { ["load", "styledata", "idle"].forEach((ev) => map.off(ev, g)); } };
    ["load", "styledata", "idle"].forEach((ev) => map.on(ev, g));
  }

  function effacerResultats() {
    marqueurs.forEach((m) => m.remove());
    marqueurs = [];
    marqueursConnus.forEach((m) => m.remove());
    marqueursConnus = [];
    $("#an-liste").innerHTML = "";
    $("#an-connus").hidden = true;
    fermerSite();
    quandPret(() => { couches(); map.getSource("an-choix").setData(vide()); });
  }

  // ------------------------------------------------------------------ résultat (panneau de droite)
  function lireCoords(c) {
    return `${nb2.format(Math.abs(c.lat))}° ${c.lat >= 0 ? "N" : "S"}, ${nb2.format(Math.abs(c.lon))}° ${c.lon >= 0 ? "E" : "W"}`;
  }
  const noms = {};                    // h3 -> nom du lieu, une fois connu

  function afficher(premier) {
    const C = classement;
    bilanVert();
    const n = C.candidats.length;
    $("#an-titre").textContent = n ? `${n} site${n > 1 ? "s" : ""} that look${n > 1 ? "" : "s"} like your area ${SUR}` : "No site found";
    $("#an-liste").innerHTML = C.candidats.map((c, i) => `
      <li><button type="button" data-i="${i}" title="Similarity: ${pct.format(c.score)}">
        <span class="analogues-rang">${i + 1}</span>
        <span class="analogues-lieu-bloc"><span class="analogues-lieu">${noms[c.h3] || lireCoords(c)}</span>${etiquetteImpact(c.impact)}${modeVert ? `<span class="analogues-vert">${resumeVert(c)}</span>` : ""}</span>
        ${pastille(c.score)}
      </button></li>`).join("") || `<li class="analogues-doux">No place passes every criterion: try other weights.</li>`;
    $("#an-liste").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => choisir(+b.dataset.i)));
    afficherConnus();
    afficherImpact();
    fermerSite();
    quandPret(() => {
      couches();
      map.getSource("an-choix").setData(vide());
      marqueurs.forEach((m) => m.remove());
      marqueurs = C.candidats.map((c, i) => {
        const el = document.createElement("button");
        el.type = "button";
        el.className = "analogues-marqueur";
        el.innerHTML = `<i></i><b>${i + 1}</b>`;     // losange tourné dessous, numéro droit dessus
        el.title = `Site ${i + 1}`;
        el.setAttribute("aria-label", `Site ${i + 1}`);
        el.addEventListener("click", (e) => { e.stopPropagation(); choisir(i); });
        return new maplibregl.Marker({ element: el }).setLngLat([c.lon, c.lat]).addTo(map);
      });
      marqueursConnus.forEach((m) => m.remove());
      marqueursConnus = C.connus.map((k, j) => {
        if (k.lat == null) return null;
        const el = document.createElement("button");
        el.type = "button";
        el.className = `connu-marqueur ${k.scope === "mineralogy" ? "hors" : ""}`;
        el.innerHTML = "<i></i>";                     // le losange : MapLibre place l'élément avec transform
        el.setAttribute("aria-label", `Known analog: ${k.name}`);
        el.title = `${k.name}: ${texteRang(k)}`;
        el.addEventListener("click", (e) => { e.stopPropagation(); choisirConnu(j); });
        return new maplibregl.Marker({ element: el }).setLngLat([k.lon, k.lat]).addTo(map);
      }).filter(Boolean);
      const c = C.candidats[0];
      if (premier && c) map.flyTo({ center: [c.lon, c.lat], zoom: zoomA(1.6, c.lat, 0.8), duration: 1500, essential: true });
    });
    nommerListe(C);
  }

  // ------------------------------------------------------------------ analogues connus
  // Couleur du rang d'un analogue connu : vert ou jaune dans le haut du classement, gris neutre au-delà de 25 %
  // (un analogue d'une autre zone, Devon pour Gale par exemple, n'a pas à ressembler : ce n'est pas un échec).
  const couleurPart = (p) => (p == null || p > 0.25 ? INCONNU.couleur : p <= 0.05 ? "#3DDC97" : p <= 0.1 ? "#B9E05A" : "#F2C14E");
  const fmtPart = (p) => (p < 0.01 ? `${nb1.format(100 * p)} %` : pct.format(p));
  function texteRang(k) {
    if (k.cause === "eau") return "at sea or on the coast: not compared";
    if (k.cause === "vegetation") return "set aside by the vegetation filter (Advanced settings)";
    if (k.cause === "protegee") return "in a protected area: set aside by the filter (Advanced settings)";
    if (k.cause === "donnees") return "too little data there";
    const r = `#${nb.format(k.rang)} of ${nb.format(k.n)} candidates`;
    return k.garde ? `${r}; passes the funnel (#${nb.format(k.rangAvec)} of the ${nb.format(k.nAvec)} left)`
      : `${r}; set aside by the funnel at the “${nomModule(k.module)}” step`;
  }
  function afficherConnus() {
    const K = classement.connus;
    $("#an-connus").hidden = !K.length;
    $("#an-connus-liste").innerHTML = K.map((k, j) => {
      const hors = k.scope === "mineralogy";
      const etiquette = hors ? "minerals" : k.part != null ? `Top ${fmtPart(k.part)}` : "set aside";
      return `<li><button type="button" data-k="${j}" class="connu${hors ? " hors" : ""}" ${k.lat == null ? "disabled" : ""}
          title="${echapper(`${k.name} (${k.country}): ${k.analog_of}. ${hors ? "Mineral analog: the tool does not compare minerals." : texteRang(k)}`)}">
        <span class="connu-nom">${echapper(k.name)}</span>
        <span class="connu-rang" style="--c:${hors || k.cause ? INCONNU.couleur : couleurPart(k.part)}">${etiquette}</span>
      </button></li>`;
    }).join("");
    $("#an-connus-liste").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => choisirConnu(+b.dataset.k)));
  }

  /** Fiche d'un analogue connu : la même que pour un site, avec son rang réel au lieu de « Site n sur 10 ». */
  function choisirConnu(j) {
    if (balayage) return;
    const k = classement && classement.connus[j];
    if (!k || k.lat == null) return;
    choisir(CONNU + j, { h3: k.cellule, lat: k.lat, lon: k.lon, score: k.score, modules: k.modules,
      entete: `Known analog · ${k.rang ? `#${nb.format(k.rang)} of ${nb.format(k.n)}` : "set aside"}`, connu: k });
  }

  /** Noms des sites : tous d'un coup (régions et pays de Natural Earth, POST /api/names), puis, pour ceux qui n'ont
   *  qu'un pays (ou rien), un à un par la fiche complète, qui interroge OpenStreetMap (une requête par seconde) : « China »
   *  devient la localité ou le comté. */
  const nomsProvisoires = new Set();
  async function nommerListe(C) {
    const manquants = C.candidats.map((c) => c.h3).filter((h) => !noms[h]);
    if (manquants.length) {
      try {
        const r = await fetch(`${API}/api/names`, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cells: manquants }) });
        if (r.ok) Object.entries((await r.json()).names).forEach(([h, p]) => {
          if (p.name) noms[h] = p.name;
          if (p.kind !== "region") nomsProvisoires.add(h);
        });
      } catch (e) { /* noms un à un ci-dessous */ }
      if (classement !== C) return;
      C.candidats.forEach((c, j) => {
        const b = $(`#an-liste button[data-i="${j}"] .analogues-lieu`);
        if (b && noms[c.h3]) b.textContent = noms[c.h3];
      });
    }
    for (const c of C.candidats) {
      if (classement !== C) return;
      if (!noms[c.h3] || nomsProvisoires.has(c.h3)) {
        try { noms[c.h3] = titreLieu((await site(c.h3)).place) || noms[c.h3] || lireCoords(c); } catch (e) { return; }
        nomsProvisoires.delete(c.h3);
      }
      const b = $(`#an-liste button[data-i="${C.candidats.indexOf(c)}"] .analogues-lieu`);
      if (b && classement === C) b.textContent = noms[c.h3];
    }
  }

  // ------------------------------------------------------------------ tester de façon responsable
  /** Impact d'une campagne d'essais sur la ligne i d'un bloc « impact » (réserve ou analogue connu) :
   *  { niveau, raisons } ; niveau null sans la WDPA (on dit seulement la distance à l'aéroport). Règles :
   *  aire protégée — au moins 20 % en protection stricte (UICN Ia à II) ou au moins la moitié protégée ;
   *  faible — moins de 10 % protégé, sur un terrain déjà transformé par des mines (au moins 0,5 % de la surface) ;
   *  moyen — le reste. Les parts sont des moyennes sur l'empreinte du site ; l'aéroport ne joue que sur l'avion. */
  // ------------------------------------------------------------------ green mode
  // Off by default, and for each new area: it only stays on for the same area, in this tab (when coming back from
  // the wrap, for example).
  const cleVert = `${VERT.cle}-${corps}-${zoneId || zone.join(",").length + ":" + zone.length}`;
  let modeVert = (() => { try { return sessionStorage.getItem(cleVert) === "1"; } catch (e) { return false; } })();
  const reglagesVert = Object.assign({ plancher: 0.9, budget: null, protege: "tout" },
    (() => { try { return JSON.parse(localStorage.getItem(VERT.cleReglages) || "{}") || {}; } catch (e) { return {}; } })());
  const garderReglages = () => { try { localStorage.setItem(VERT.cleReglages, JSON.stringify(reglagesVert)); } catch (e) { /* private browsing */ } };
  /** Protected area to set aside: "tout" (10% of the footprint, or of strict protection), or only "strict". */
  function exclueProtegee(I, i) {
    const st = I.strict ? I.strict[i] ?? 0 : 0, pr = I.protected ? I.protected[i] ?? 0 : 0;
    return st >= VERT.strictMax || (reglagesVert.protege === "tout" && pr >= VERT.protegeMax);
  }
  /** Impact of a campaign on row i: CO₂ of the flight from the departure city (t per person, round trip), otherwise
   *  distance to the airport (in thousands of km); ground already transformed by mines counts a little less. */
  function coutVert(I, i) {
    const mines = I.mines && (I.mines[i] ?? 0) >= MINES_MIN ? 0.05 : 0;
    if (depart) {
      const [la, lo] = H.cellToLatLng(R.pool.h3[i]), v = texteVol(la, lo);
      return { co2: v.t, cout: v.t - mines };
    }
    const a = I.airport_km ? I.airport_km[i] : null;
    return { co2: null, cout: (a == null ? 9 : a / 1000) - mines };
  }
  /** What ranks a site in green mode, in a few words (in the list). */
  function resumeVert(c) {
    if (depart) { const v = texteVol(c.lat, c.lon); return v.t ? `${fmtCo2(v.t)} CO₂e` : "by land"; }
    return c.impact && c.impact.aeroport != null ? `airport ${nb.format(c.impact.aeroport)} km` : "";
  }
  function appliquerModeVert() {
    document.body.classList.toggle("mode-vert", modeVert);
    panneau.querySelectorAll(".vert-bascule").forEach((b) => b.setAttribute("aria-checked", String(modeVert)));
    $("#an-protegees-case").classList.toggle("inactif", modeVert);   // protected areas are already set aside
  }
  /** What green mode changes compared with the usual ranking (the 10 sites, on average). */
  function gainsVert() {
    const C = classement;
    if (!modeVert || !C || !C.standard || !C.candidats.length) return null;
    const moy = (l, f) => { const v = l.map(f).filter((x) => x != null); return v.length ? v.reduce((a, x) => a + x, 0) / v.length : null; };
    const g = {
      proteges: C.standard.filter((c) => R.pool.impact && exclueProtegee(R.pool.impact, c.i)).length,
      aeroport: [moy(C.standard, (c) => c.impact && c.impact.aeroport), moy(C.candidats, (c) => c.impact && c.impact.aeroport)],
      score: [moy(C.standard, (c) => c.score), moy(C.candidats, (c) => c.score)],
      co2: depart ? [moy(C.standard, (c) => texteVol(c.lat, c.lon).t), moy(C.candidats, (c) => texteVol(c.lat, c.lon).t)] : null,
    };
    g.perte = Math.round(100 * (g.score[0] - g.score[1]));
    return g;
  }
  /** The line under the switch of the header. */
  function bilanVert() {
    const el = $("#an-vert-bilan"), g = gainsVert();
    if (!el) return;
    if (!g) { el.hidden = true; return; }
    const morceaux = [];
    if (g.co2 && g.co2[0] - g.co2[1] >= 0.05) morceaux.push(`${fmtCo2(g.co2[0] - g.co2[1])} CO₂e less per person`);
    else if (g.aeroport[0] != null && g.aeroport[1] != null && g.aeroport[0] - g.aeroport[1] >= 5) morceaux.push(`airports ${nb.format(g.aeroport[0] - g.aeroport[1])} km closer`);
    morceaux.push(g.proteges ? `${g.proteges} protected site${g.proteges > 1 ? "s" : ""} set aside` : "no protected site");
    morceaux.push(g.perte > 0 ? `similarity −${g.perte} pt${g.perte > 1 ? "s" : ""}` : "similarity unchanged");
    el.textContent = morceaux.join(" · ");
    el.hidden = false;
  }

  function impactSite(I, i) {
    if (!I) return null;
    const val = (x) => (x && x[i] != null ? x[i] : null);
    const p = val(I.protected), s = val(I.strict), m = val(I.mines), a = val(I.airport_km);
    const raisons = [];
    if (p != null) raisons.push(p >= 0.01 ? `${pct.format(p)} in protected areas${s >= 0.01 ? ` (${pct.format(s)} strictly protected)` : ""}` : "no protected area");
    if (m != null && m >= MINES_MIN) raisons.push(`mines on ${m < 0.01 ? nb1.format(100 * m) : nb.format(100 * m)}% of the land: already transformed`);
    if (a != null) raisons.push(`${nb.format(a)} km from an airport with scheduled flights`);
    let n = null;
    if (p != null) {
      if ((s ?? 0) >= 0.2 || p >= 0.5) n = IMPACT.haut;
      else if (p < 0.1 && (m ?? 0) >= MINES_MIN) n = IMPACT.bas;
      else n = IMPACT.moyen;
    }
    const faits = [p == null ? null : p >= 0.01 ? `${pct.format(p)} protected` : "not protected",
      m != null && m >= MINES_MIN ? `mines ${m < 0.01 ? nb1.format(100 * m) : nb.format(100 * m)}%` : null,
      a != null ? `airport ${nb.format(a)} km` : null].filter(Boolean);
    const texte = n === IMPACT.moyen ? (p >= 0.1 ? "partly in protected areas" : "outside protected areas, but on land that nothing has transformed yet")
      : n ? n.texte : "";
    return { niveau: n, texte, raisons, faits, protege: p, aeroport: a };
  }
  const etiquetteImpact = (im) => (!im || !im.niveau || im.niveau === IMPACT.moyen ? "" :
    `<span class="impact-tag ${im.niveau.cle}" title="${echapper(im.raisons.join(" · "))}">${im.niveau.nom}</span>`);

  /** t CO₂e par personne, aller-retour en avion, pour une distance à vol d'oiseau en km. */
  function co2Vol(km) {
    const d = km * VOL.detour;
    return (2 * d * (d < VOL.seuilKm ? VOL.court : VOL.long)) / 1000;
  }
  const fmtCo2 = (t) => (t < 0.1 ? "< 0.1 t" : `${nb1.format(t)} t`);
  function texteVol(lat, lon) {
    if (!depart) return null;
    const km = distanceKm(depart.lat, depart.lon, lat, lon);
    return km < VOL.terreKm
      ? { km, t: 0, html: `${nb.format(km)} km from ${echapper(depart.nom)}: reachable by land`, court: `${nb.format(km)} km, by land` }
      : { km, t: co2Vol(km), html: `${nb.format(km)} km from ${echapper(depart.nom)}: <b>${fmtCo2(co2Vol(km))} CO₂e</b> per person, round trip by plane`,
        court: `<b>${fmtCo2(co2Vol(km))} CO₂e</b> by plane` };
  }

  // Ville de départ : gardée dans le navigateur ; liste de Natural Earth (js/villes.js), ou la position du navigateur
  let depart = (() => {
    try { const d = JSON.parse(localStorage.getItem(CLE_DEPART) || "null"); return d && Number.isFinite(d.lat) && Number.isFinite(d.lon) ? d : null; }
    catch (e) { return null; }
  })();
  const sansAccent = (t) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const libelleVille = (v) => [v[0], v[1] && v[1] !== v[0] ? v[1] : null, v[2]].filter(Boolean).join(", ");
  function choisirDepart(d, libelle) {
    depart = d;
    try { if (d) localStorage.setItem(CLE_DEPART, JSON.stringify(d)); else localStorage.removeItem(CLE_DEPART); } catch (e) { /* private browsing */ }
    $("#an-depart").value = d ? libelle || d.nom : "";
    if (modeVert && R) recalculer();               // the flight from the city counts in the green ranking
    afficherImpact();
  }
  /** Branche le champ de ville de départ (et son bouton de position) du panneau de droite. */
  function preparerDepart(racine = panneau) {
    const champ = racine.querySelector(".impact-depart input"), liste = racine.querySelector(".impact-depart datalist");
    const bouton = racine.querySelector(".impact-ici");
    if (!champ) return;
    if (depart && !champ.value) champ.value = depart.nom;
    champ.addEventListener("input", () => {
      const q = sansAccent(champ.value.trim());
      if (q.length < 2) { liste.innerHTML = ""; return; }
      const debut = [], dedans = [];
      for (const v of VILLES) {
        const nom = sansAccent(v[0]);
        if (nom.startsWith(q)) debut.push(v); else if (nom.includes(q)) dedans.push(v);
        if (debut.length >= 8) break;
      }
      liste.innerHTML = debut.concat(dedans).slice(0, 8).map((v) => `<option value="${echapper(libelleVille(v))}"></option>`).join("");
    });
    champ.addEventListener("change", () => {
      const t = champ.value.trim();
      if (!t) { choisirDepart(null); return; }
      const q = sansAccent(t);
      const v = VILLES.find((x) => sansAccent(libelleVille(x)) === q) || VILLES.find((x) => sansAccent(x[0]) === q.split(",")[0].trim());
      if (v) choisirDepart({ nom: v[0], lat: v[3], lon: v[4] }, libelleVille(v));
      else {
        racine.querySelectorAll(".impact-inconnue").forEach((e) => e.remove());
        champ.closest(".impact-depart").insertAdjacentHTML("beforeend", `<p class="analogues-erreur impact-inconnue">“${echapper(t)}” is not in the list of cities: pick one from the suggestions.</p>`);
      }
    });
    if (bouton) bouton.addEventListener("click", () => {
      if (!navigator.geolocation) return;
      navigator.geolocation.getCurrentPosition((p) => {
        choisirDepart({ nom: "your location", lat: +p.coords.latitude.toFixed(3), lon: +p.coords.longitude.toFixed(3) }, "My location");
      }, () => { champ.placeholder = "Location refused: type a city"; }, { timeout: 10000 });
    });
  }

    /** The "Responsible testing" panel: the settings of green mode and what it changes in the list of 10 sites. */
  function afficherImpact() {
    const C = classement, bloc = $("#an-impact-cartes");
    if (!C || !R) return;
    const I = R.pool.impact, P = R.pool;
    const premier = C.candidats[0];
    const carte = (titre, x, texte) => `<button type="button" class="impact-carte" data-i="${x.i}" data-entete="${echapper(titre)}">
        <span class="impact-carte-titre">${titre}</span>
        <span class="impact-carte-nom" data-h3="${P.h3[x.i]}">${echapper(noms[P.h3[x.i]] || lireCoords(x))}</span>
        ${etiquetteImpact(x.impact)}
        <span class="impact-carte-texte">${texte}</span></button>`;
    const faitsSite = (c) => [...(c.impact ? c.impact.faits : []), depart ? texteVol(c.lat, c.lon).court : null, `${pct.format(c.score)} similar`].filter(Boolean).join(" · ");

    // green mode settings: they change the 10 sites directly
    const reg = $("#an-vert-reglages");
    const choix = (cle, valeurs, nom, actif, inactif = () => false) => `<div class="an-ecart">${valeurs.map((v) =>
      `<button type="button" data-${cle}="${v ?? ""}" aria-pressed="${actif(v)}" ${inactif(v) ? "disabled" : ""}>${nom(v)}</button>`).join("")}</div>`;
    reg.hidden = !modeVert;
    reg.innerHTML = modeVert ? `
      <div class="vert-reglage"><span>Similarity floor <em>vs the best site</em></span>
        ${choix("plancher", VERT.planchers, (v) => pct.format(v), (v) => reglagesVert.plancher === v)}</div>
      <div class="vert-reglage"><span>CO₂ budget <em>per person, round trip</em></span>
        ${choix("budget", VERT.budgets, (v) => (v == null ? "None" : `${nb1.format(v)} t`), (v) => reglagesVert.budget === v, (v) => v != null && !depart)}</div>
      <div class="vert-reglage"><span>Protected areas</span>
        ${choix("protege", ["tout", "strict"], (v) => (v === "tout" ? "All excluded" : "Strict only"), (v) => reglagesVert.protege === v)}</div>` : "";
    reg.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
      if (b.dataset.plancher) reglagesVert.plancher = +b.dataset.plancher;
      if ("budget" in b.dataset) reglagesVert.budget = b.dataset.budget ? +b.dataset.budget : null;
      if (b.dataset.protege) reglagesVert.protege = b.dataset.protege;
      garderReglages();
      fermerSite();
      recalculer();
    }));

    const cartes = [];
    if (!modeVert) {
      if (premier) cartes.push(carte("Your site 1", premier, faitsSite(premier)));
      cartes.push(`<p class="vert-invite">Turn on <b>Green mode</b> above: the 10 sites become the lowest-impact ones among those that look enough like your area.</p>`);
    } else if (!premier) {
      cartes.push(`<p class="vert-invite">No site passes these limits: raise the CO₂ budget or lower the similarity floor.</p>`);
    } else {
      const g = gainsVert(), chiffres = [];
      if (g && g.co2) {
        const d = g.co2[0] - g.co2[1];
        chiffres.push([d >= 0.05 ? `−${fmtCo2(d)}` : "≈ 0 t", `CO₂e per person on average${d >= 0.05 ? `, −${fmtCo2(d * VERT.equipe)} for a team of ${VERT.equipe}` : ""}`]);
      } else if (g && g.aeroport[0] != null && g.aeroport[1] != null) {
        const d = g.aeroport[0] - g.aeroport[1];
        chiffres.push([d >= 5 ? `−${nb.format(d)} km` : "≈ 0 km", "to the nearest airport, on average. Add a departure city to count the flights."]);
      }
      if (g) {
        chiffres.push([nb.format(g.proteges), `protected site${g.proteges === 1 ? "" : "s"} of the usual list set aside`]);
        chiffres.push([g.perte > 0 ? `−${g.perte} pt${g.perte > 1 ? "s" : ""}` : "0 pt", "of similarity on average: the price of the greener list"]);
      }
      cartes.push(`<div class="vert-gains">${chiffres.map(([n, t]) => `<p><b>${n}</b> ${t}</p>`).join("")}</div>`);
      cartes.push(carte("Your greenest good site", premier, faitsSite(premier)));
    }
    bloc.innerHTML = cartes.join("");
    bloc.querySelectorAll(".impact-carte").forEach((b) => b.addEventListener("click", () => ouvrirLigne(+b.dataset.i, b.dataset.entete)));
    const wdpa = I && I.source ? (I.source.match(/\(([^)]*)\), Protected Planet: [^,]*, ([^,]+),/) || []) : [];
    $("#an-impact-sources").innerHTML = [I && I.source ? `Protected areas: UNEP-WCMC and IUCN (${wdpa[1] || ""}), Protected Planet,
        WDPA ${wdpa[2] || ""}, <a href="https://www.protectedplanet.net" target="_blank" rel="noopener">protectedplanet.net</a>` : null,
      I && I.airport_km ? "airports: OurAirports" : null, I && I.mines ? "mines: Maus et al. 2022" : null,
      depart ? "flights: UK GHG factors 2025, economy, +8% detours, round trip" : null]
      .filter(Boolean).join(" · ");
    // noms des sites hors de la liste, quand ils arrivent
    bloc.querySelectorAll(".impact-carte-nom").forEach((el) => {
      const h = el.dataset.h3;
      if (noms[h]) return;
      site(h).then((d) => { const n = titreLieu(d.place); if (n) { noms[h] = n; el.textContent = n; } }).catch(() => {});
    });
  }

  /** Fiche d'une ligne de la réserve : celle de la liste si le site y est, sinon une fiche « hors liste ». */
  function ouvrirLigne(i, entete) {
    const C = classement;
    const j = C.candidats.findIndex((c) => c.i === i);
    if (j >= 0) { choisir(j); return; }
    const P = R.pool, [lat, lon] = H.cellToLatLng(P.h3[i]);
    const actifs = R.active_modules.filter((m) => (poids[m] ?? 0) > 0);
    choisir(AUTRE, { h3: P.h3[i], lat, lon, score: C.scores[i], impact: impactSite(P.impact, i), entete,
      modules: Object.fromEntries(actifs.map((m) => [m, P.score_per_module[m][i]])) });
  }

  // ------------------------------------------------------------------ « Pourquoi ce site ? »
  /** Une variable comparable de chaque critère : la vedette la plus ressemblante (ou la plus différente). */
  function variableParlante(m, plusProche) {
    const ved = (VEDETTES[m.key] || []);
    const vars = m.variables.filter((v) => v.compared && v.similarity != null && v.reference != null && v.earth != null);
    // Une ressemblance « parlante » : les vedettes d'abord, et une présence partagée avant une absence partagée.
    const rang = (v) => (ved.includes(v.key) ? 0 : 2) + (absent(v) ? 1 : 0);
    return vars.sort((a, b) => rang(a) - rang(b) || (plusProche ? b.similarity - a.similarity : a.similarity - b.similarity))[0];
  }

  /** « pas de dunes, comme sur Mars » quand les deux valent ~0, sinon les deux valeurs. */
  const absent = (v) => v.mode === "abs" && !v.unit && typeof v.earth === "number" && typeof v.reference === "number"
    && v.earth <= 0.01 && v.reference <= 0.01;
  function phrase(v) {
    const nom = COURTS[v.key] || v.label.replace(/ \(.*\)$/, "").toLowerCase();
    if (absent(v)) return `no ${nom}, as ${SUR}`;
    return `${nom}: <b style="color:${COULEUR_TERRE}">${lisible(v.earth, v, "earth")}</b> here, <b style="color:${COULEUR_CORPS[corps]}">${lisible(v.reference, v, "reference")}</b> ${SUR}`;
  }

  function sensDifference(v) {
    if (v.mode === "hellinger") return "the rocks are not the same";
    if (typeof v.earth !== "number" || typeof v.reference !== "number") return "";
    const plus = v.earth > v.reference;
    if (v.unit === "K" && v.key !== "amplitude") return plus ? "it is warmer here" : "it is colder here";
    const nom = COURTS[v.key] || "this value";
    return `${plus ? "more" : "less"} ${nom} here`;
  }

  function pourquoi(detail) {
    const mods = (detail.modules || []).filter((m) => (poids[m.key] ?? 0) > 0 && m.similarity != null);
    if (!mods.length) return `<p class="analogues-doux">Not enough data to explain this site.</p>`;
    const tri = mods.slice().sort((a, b) => b.similarity - a.similarity);
    const communs = tri.filter((m) => m.similarity >= 0.6).slice(0, 3).map((m) => variableParlante(m, true)).filter(Boolean);
    const pire = tri[tri.length - 1];
    const diff = pire && pire.similarity < 0.6 ? variableParlante(pire, false) : null;
    return `
      ${communs.length ? `<p class="pourquoi-titre">Like your area ${SUR}:</p>
        <ul class="pourquoi-liste">${communs.map((v) => `<li>${phrase(v)}</li>`).join("")}</ul>` : ""}
      ${diff ? `<p class="pourquoi-titre pourquoi-diff">The biggest difference${sensDifference(diff) ? ": " + sensDifference(diff) : ""}</p>
        <ul class="pourquoi-liste"><li>${phrase(diff)}</li></ul>`
        : `<p class="pourquoi-titre">No big difference on the measured criteria.</p>`}`;
  }

  // ------------------------------------------------------------------ critères Mars ⟷ Terre
  /** Un critère : une ligne (nom, mot de couleur) ; dépliée, ses deux variables vedettes côte à côte. */
  function carteCritere(cle, s, detail) {
    const n = niveau(s);
    const tete = `<summary><span class="critere-nom">${nomModule(cle)}</span>${mot(s)}</summary>`;
    if (!detail) return `<details class="critere" data-module="${cle}" style="--c:${n.couleur}">${tete}<p class="analogues-doux">…</p></details>`;
    const ved = VEDETTES[cle] || [];
    const vars = detail.variables.filter((v) => ved.includes(v.key));
    return `<details class="critere" data-module="${cle}" style="--c:${n.couleur}">${tete}
      <div class="duel-lignes">${(vars.length ? vars : detail.variables.slice(0, 2)).map(ligneDuel).join("")}</div></details>`;
  }

  /** Une variable : la zone à gauche, la Terre à droite, et entre les deux l'écart sur une échelle commune. */
  function ligneDuel(v) {
    const n = v.compared ? niveau(v.similarity) : INCONNU;
    const titre = COURTS[v.key] || v.label.replace(/ \(.*\)$/, "");
    if (v.mode === "hellinger") {
      return `<div class="duel-ligne duel-parts" style="--c:${n.couleur}">
        <span class="duel-label">${titre}${v.compared ? "" : ' <em title="The Earth data do not contain these classes">not comparable</em>'}</span>
        ${barreParts(v.reference, COULEUR_CORPS[corps])}${barreParts(v.earth, COULEUR_TERRE)}
        <span class="duel-valeurs"><span>${lisible(v.reference, v, "reference")}</span><span>${lisible(v.earth, v, "earth")}</span></span>
      </div>`;
    }
    const a = v.mode === "deciles" ? (v.reference || [])[4] : v.reference;
    const b = v.mode === "deciles" ? (v.earth || [])[4] : v.earth;
    let [lo, hi] = v.range || [0, 1];
    [a, b].forEach((x) => { if (x != null) { lo = Math.min(lo, x); hi = Math.max(hi, x); } });
    const pos = (x) => (x == null || hi <= lo ? null : 100 * (x - lo) / (hi - lo));
    const pa = pos(a), pb = pos(b);
    const segment = pa != null && pb != null ? `<i class="duel-ecart" style="left:${Math.min(pa, pb)}%;width:${Math.abs(pa - pb)}%"></i>` : "";
    return `<div class="duel-ligne" style="--c:${n.couleur}">
      <span class="duel-label">${titre}</span>
      <span class="duel-gauche">${lisible(v.reference, v, "reference")}</span>
      <span class="duel-piste" aria-hidden="true">${segment}
        ${pa != null ? `<i class="duel-point" style="left:${pa}%;--p:${COULEUR_CORPS[corps]}"></i>` : ""}
        ${pb != null ? `<i class="duel-point" style="left:${pb}%;--p:${COULEUR_TERRE}"></i>` : ""}</span>
      <span class="duel-droite">${lisible(v.earth, v, "earth")}</span>
    </div>`;
  }

  function barreParts(parts, couleurBord) {
    if (!parts) return `<span class="parts parts-vide" style="--b:${couleurBord}"></span>`;
    const tri = Object.entries(parts).filter(([, x]) => x != null && x > 0.01).sort((a, b) => b[1] - a[1]);
    return `<span class="parts" style="--b:${couleurBord}">${tri.map(([k, x]) =>
      `<i style="width:${100 * x}%;background:${COULEUR_CLASSE[k] || "#999"}" title="${CLASSES[k] || k} ${pct.format(x)}"></i>`).join("")}</span>`;
  }

  // ------------------------------------------------------------------ fiche du site (modale à gauche)
  const fiche = document.createElement("aside");
  fiche.className = "site";
  fiche.setAttribute("role", "dialog");
  fiche.setAttribute("aria-labelledby", "site-titre");
  fiche.hidden = true;
  document.body.appendChild(fiche);
  let ouverte = -1;
  const cacheSite = {};

  async function site(cellule) {
    if (!cacheSite[cellule]) {
      cacheSite[cellule] = fetch(`${API}/api/site/${cellule}`).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });
    }
    try { return await cacheSite[cellule]; } catch (e) { delete cacheSite[cellule]; throw e; }
  }

  const titreLieu = (p) => (p && p.name) || null;
  function sousTitreLieu(p) {
    if (!p) return "";
    const morceaux = [];
    const nat = (p.natural_regions || [])[0];
    if (nat && nat.kind) morceaux.push(nat.kind.charAt(0).toUpperCase() + nat.kind.slice(1));
    [p.locality, p.state, p.country].forEach((x) => { if (x && x !== p.name && !morceaux.includes(x)) morceaux.push(x); });
    return morceaux.map(echapper).join(" · ");
  }

  function fermerSite() {
    if (ouverte < 0 && fiche.hidden) return;
    ouverte = -1;
    siteOuvert = null;
    fiche.hidden = true;
    marqueurs.forEach((m) => m.getElement().classList.remove("actif"));
    $("#an-liste").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", "false"));
    $("#an-connus-liste").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", "false"));
    if (classement && map.getSource("an-choix")) map.getSource("an-choix").setData(vide());
  }

  // ------------------------------------------------------------------ données côte à côte (onglet Data de la fiche)
  // Toutes les variables comparées : la zone de Mars ou de la Lune d'un côté, le site de la Terre de l'autre
  // (POST /api/search/detail : moyennes sur la zone et sur l'empreinte du site), et leur ressemblance.
  function afficherComparaison(c) {
    const d = c.detail, el = fiche.querySelector("#site-data");
    if (!el) return;
    if (!d || !(d.modules || []).length) { el.innerHTML = `<p class="analogues-doux">No comparable data for this site.</p>`; return; }
    const groupes = d.modules.map((m) => `<tbody>
        <tr class="cg"><th scope="rowgroup" colspan="3">${nomModule(m.key)}</th><td class="cm">${m.similarity != null ? pastille(m.similarity) : ""}</td></tr>
        ${m.variables.map((v) => `<tr><th scope="row">${echapper((COURTS[v.key] || v.label.replace(/ \(.*\)$/, "")).replace(/^./, (x) => x.toUpperCase()))}</th>
          <td class="cz">${echapper(lisible(v.reference, v, "reference"))}</td><td class="ct">${echapper(lisible(v.earth, v, "earth"))}</td>
          <td class="cm">${v.compared && v.similarity != null ? `<span class="mot" style="--c:${niveau(v.similarity).couleur}">${pct.format(v.similarity)}</span>`
            : `<span class="analogues-doux">–</span>`}</td></tr>`).join("")}</tbody>`).join("");
    el.innerHTML = `<div class="comparaison" style="--zone:${COULEUR_CORPS[corps]}">
        <table><thead><tr><th scope="col">Variable</th><th scope="col" class="cz">${NOMS[corps].replace(/^the /, "The ")}</th>
          <th scope="col" class="ct">Earth</th><th scope="col" class="cm">Match</th></tr></thead>${groupes}</table></div>`;
  }

  // Onglets de la fiche : Overview (pourquoi, critères), Data (tableau) ; le dernier choisi est gardé.
  // L'impact d'une campagne d'essais est dans l'onglet « Responsible testing » du panneau de droite.
  const ONGLETS_SITE = [{ cle: "apercu", nom: "Overview" }, { cle: "donnees", nom: "Data" }];
  let ongletSite = "apercu";
  function ouvrirOngletSite(cle, focus = false) {
    ongletSite = cle;
    fiche.querySelectorAll('.site-onglets [role="tab"]').forEach((b) => {
      const oui = b.dataset.onglet === cle;
      b.setAttribute("aria-selected", String(oui));
      b.tabIndex = oui ? 0 : -1;
      if (oui && focus) b.focus();
    });
    fiche.querySelectorAll(".site-vue").forEach((v) => { v.hidden = v.dataset.onglet !== cle; });
    fiche.classList.toggle("large", cle === "donnees");
  }

  const CONNU = 100;                  // fiche ouverte d'un analogue connu : CONNU + son rang dans l'encart
  const AUTRE = 200;                  // fiche ouverte d'un site hors de la liste (alternative à faible impact, à portée)
  let siteOuvert = null;
  let siteReplie = false;
  function choisir(i, connu = null) {
    if (balayage) return;
    const C = classement;
    const c = connu || (C && C.candidats[i]);
    if (!c) return;
    ouverte = i;
    prechargerRelief(c);
    $("#an-connus-liste").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(CONNU + +b.dataset.k === i)));
    $("#an-liste").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(+b.dataset.i === i)));
    marqueurs.forEach((m, j) => m.getElement().classList.toggle("actif", j === i));
    const empreinte = R.footprint && R.footprint.rings ? H.gridDisk(c.h3, R.footprint.rings) : [c.h3];
    quandPret(() => { couches(); map.getSource("an-choix").setData({ type: "FeatureCollection", features: contourEmpreinte(empreinte) }); });
    map.flyTo({ center: [c.lon, c.lat], zoom: zoomA(7.8, c.lat, 5), duration: 1600, essential: true });

    const n = niveau(c.score);
    fiche.innerHTML = `
      <div class="site-barre">
        <span class="site-rang">${connu ? connu.entete : `Site ${i + 1} of ${C.candidats.length}`}</span>
        <span>
          ${connu ? "" : `<button type="button" class="site-nav" data-d="-1" aria-label="Previous site" ${i === 0 ? "disabled" : ""}>‹</button>
          <button type="button" class="site-nav" data-d="1" aria-label="Next site" ${i === C.candidats.length - 1 ? "disabled" : ""}>›</button>`}
          <button type="button" class="site-replier" aria-expanded="${!siteReplie}" aria-label="${siteReplie ? "Expand" : "Collapse"} the site card" title="Collapse"><svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 10l4-4 4 4"/></svg></button>
          <button type="button" class="site-fermer" aria-label="Close the site card">×</button>
        </span>
      </div>
      <h2 id="site-titre">${echapper(connu && connu.connu ? connu.connu.name : noms[c.h3] || lireCoords(c))}</h2>
      <p class="site-sous-titre" id="site-sous-titre"></p>
      ${connu && connu.connu ? `<p class="site-connu">Known analog for ${echapper(connu.connu.analog_of)} (${echapper(connu.connu.source)}).
        ${echapper(texteRang(connu.connu))}${connu.connu.scope === "mineralogy" ? ". The tool does not compare minerals: this rank says nothing about the analogy." : "."}</p>` : ""}
      <p class="site-verdict" style="--c:${n.couleur}"><b>${n.nom}</b> to your area ${SUR} · <b>${pct.format(c.score)}</b> similar</p>
      <div class="site-actions">
        <button type="button" class="site-bilan" id="site-bilan" title="Your AstroWrap: an animated recap of the comparison, in a separate page">
          <span class="site-bilan-titre">▶ Play the AstroWrap</span></button>
        ${window.vue3D ? `<button type="button" class="site-3d" id="site-3d">Compare the terrain</button>` : ""}
      </div>
      <div class="site-onglets" role="tablist" aria-label="Site card">
        ${ONGLETS_SITE.map((o) => `<button type="button" role="tab" id="site-onglet-${o.cle}" data-onglet="${o.cle}" aria-controls="site-vue-${o.cle}"
          aria-selected="${o.cle === ongletSite}" tabindex="${o.cle === ongletSite ? 0 : -1}">${o.nom}</button>`).join("")}
      </div>
      <div class="site-vue" id="site-vue-donnees" data-onglet="donnees" role="tabpanel" aria-labelledby="site-onglet-donnees" ${ongletSite === "donnees" ? "" : "hidden"}>
        <div id="site-data"><p class="analogues-doux">Loading…</p></div>
      </div>
      <div class="site-vue" id="site-vue-apercu" data-onglet="apercu" role="tabpanel" aria-labelledby="site-onglet-apercu" ${ongletSite === "apercu" ? "" : "hidden"}>
      <section class="pourquoi" id="site-pourquoi"><h3>Why this site?</h3><p class="analogues-doux">…</p></section>
      <section class="criteres">
        <div class="criteres-tete"><span style="color:${COULEUR_CORPS[corps]}">● ${NOMS[corps].replace(/^the /, "The ")}</span>
          <span style="color:${COULEUR_TERRE}">● Earth</span></div>
        ${Object.entries(c.modules).map(([cle, s]) => carteCritere(cle, s, null)).join("")}
      </section>
      <details class="site-plus"><summary>More about this site</summary>
        <div id="site-fiche"><p class="analogues-doux">Loading…</p></div>
        <section class="site-wiki" id="site-wiki" hidden><h3>Nearby (Wikipedia)</h3><ul></ul></section>
        <p class="site-credits" id="site-credits"></p>
      </details>
      </div>`;
    fiche.hidden = false;
    fiche.scrollTop = 0;
    fiche.classList.toggle("replie", siteReplie);
    siteOuvert = c;
    ouvrirOngletSite(ongletSite);
    const ongletsSite = [...fiche.querySelectorAll('.site-onglets [role="tab"]')];
    ongletsSite.forEach((b, k) => {
      b.addEventListener("click", () => ouvrirOngletSite(b.dataset.onglet));
      b.addEventListener("keydown", (e) => {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        e.preventDefault();
        ouvrirOngletSite(ongletsSite[(k + (e.key === "ArrowRight" ? 1 : ongletsSite.length - 1)) % ongletsSite.length].dataset.onglet, true);
      });
    });
    fiche.querySelector(".site-replier").addEventListener("click", (e) => {
      siteReplie = fiche.classList.toggle("replie");
      e.currentTarget.setAttribute("aria-expanded", String(!siteReplie));
      e.currentTarget.setAttribute("aria-label", `${siteReplie ? "Expand" : "Collapse"} the site card`);
    });
    fiche.querySelector(".site-fermer").addEventListener("click", fermerSite);
    const bouton3D = fiche.querySelector("#site-3d");
    if (bouton3D) bouton3D.addEventListener("click", () => {
      const topo = c.detail && (c.detail.modules || []).find((m) => m.key === "topography");
      const v = topo && topo.variables.find((x) => x.key === "slopes");
      window.vue3D.ouvrir({
        api: API, corps, zone, pentes: v ? { zone: v.reference, site: v.earth } : null,
        site: { lat: c.lat, lon: c.lon, h3: c.h3, empreinte, nom: noms[c.h3] || lireCoords(c) },
      });
    });
    fiche.querySelectorAll(".site-nav").forEach((b) => b.addEventListener("click", () => choisir(i + +b.dataset.d)));
    fiche.querySelector("#site-bilan").addEventListener("click", () => ouvrirBilan(c, i < CONNU ? i + 1 : null));

    // Nom du lieu et fiche du site sur Terre
    site(c.h3).then((d) => {
      if (ouverte !== i || classement !== C) return;
      const nom = titreLieu(d.place) || lireCoords(c);
      noms[c.h3] = nom;
      if (!connu || !connu.connu) fiche.querySelector("#site-titre").textContent = nom;
      fiche.querySelector("#site-sous-titre").innerHTML = sousTitreLieu(d.place);
      const li = $(`#an-liste button[data-i="${i}"] .analogues-lieu`);
      if (li) li.textContent = nom;
      fiche.querySelector("#site-fiche").innerHTML = d.sections.map((s) => `
        <section class="site-section"><h3>${s.name}</h3><dl>
          ${s.items.map((x) => `<dt>${x.label}</dt><dd>${typeof x.value === "number" ? nb1.format(x.value) : echapper(x.value)}${x.unit === "%" ? "%" : x.unit ? " " + x.unit : ""}</dd>`).join("")}
        </dl></section>`).join("");
      const sources = (d.place.sources || []).map((s) => (s === "OpenStreetMap" ? "© OpenStreetMap contributors" : s));
      fiche.querySelector("#site-credits").textContent = sources.length ? `Place names: ${sources.join(", ")}.` : "";
    }).catch(() => {
      if (ouverte !== i) return;
      fiche.querySelector("#site-fiche").innerHTML = `<p class="analogues-erreur">Site card unavailable: ${messageServeur()}</p>`;
    });

    // Correspondance variable par variable : « Pourquoi ce site ? » et les critères
    fetch(`${API}/api/search/detail`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: corps, h3_cells: zone, cell: c.h3 }) }).then((r) => r.json()).then((d) => {
      c.detail = d;
      if (ouverte !== i) return;
      afficherComparaison(c);
      fiche.querySelector("#site-pourquoi").innerHTML = `<h3>Why this site?</h3>${pourquoi(d)}`;
      (d.modules || []).forEach((m) => {
        const el = fiche.querySelector(`.critere[data-module="${m.key}"]`);
        if (el) el.outerHTML = carteCritere(m.key, c.modules[m.key], m);
      });
    }).catch(() => {
      if (ouverte === i) fiche.querySelector("#site-pourquoi").innerHTML = `<h3>Why this site?</h3><p class="analogues-erreur">${messageServeur()}</p>`;
    });

    // Articles Wikipédia à moins de 10 km (API publique, sans clé)
    const url = `https://en.wikipedia.org/w/api.php?action=query&list=geosearch&gscoord=${c.lat.toFixed(4)}%7C${c.lon.toFixed(4)}` +
      `&gsradius=10000&gslimit=5&format=json&origin=*`;
    fetch(url).then((r) => r.json()).then((d) => {
      const pages = (d.query && d.query.geosearch) || [];
      if (ouverte !== i || !pages.length) return;
      fiche.querySelector("#site-wiki ul").innerHTML = pages.map((p) => `<li><a href="https://en.wikipedia.org/?curid=${p.pageid}" target="_blank" rel="noopener">${echapper(p.title)}</a>
        <span class="analogues-doux">${nb1.format(p.dist / 1000)} km</span></li>`).join("");
      fiche.querySelector("#site-wiki").hidden = false;
    }).catch(() => {});
  }

  /** Bilan animé d'un site (bilan.html, page à part) : la zone passe par le serveur, les poids et le score par l'adresse. */
  async function ouvrirBilan(c, rang = null) {
    const fenetre = window.open("about:blank", "_blank");
    if (!zoneId) {
      try {
        const r = await fetch(`${API}/api/zones`, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ body: corps, h3_cells: zone }) });
        if (r.ok) zoneId = (await r.json()).id;
      } catch (e) { /* le bilan relira la zone dans le navigateur */ }
    }
    const q = new URLSearchParams();
    if (new URLSearchParams(location.search).get("api")) q.set("api", API);
    q.set("w", Object.entries(poids).map(([k, v]) => `${k}:${v}`).join(","));
    q.set("s", String(c.score));
    if (!$("#an-vegetation").checked) q.set("v", "0");
    if ($("#an-protegees").checked || modeVert) q.set("p", "1");
    if (modeVert) {
      q.set("g", "1");
      const s1 = classement && classement.standard && classement.standard[0];
      if (s1 && s1.i !== c.i) q.set("ref", `${s1.lat.toFixed(3)},${s1.lon.toFixed(3)}`);
    }
    if (rang) q.set("n", `${rang}/${classement ? classement.candidats.length : N_CANDIDATS}`);
    const url = `bilan.html?${q}#${corps}/${zoneId || "-"}/${c.h3}`;
    if (fenetre) fenetre.location.href = url; else location.href = url;
  }

  // Échap ferme la fiche avant de recentrer le globe ; flèches gauche et droite : site précédent et suivant.
  window.addEventListener("keydown", (e) => {
    if (fiche.hidden || ouverte < 0 || /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
    if (e.target.closest && e.target.closest('[role="tablist"]') && e.key !== "Escape") return;   // flèches des onglets
    if (e.key === "Escape") { e.stopImmediatePropagation(); fermerSite(); }
    else if (ouverte >= CONNU) return;
    else if (e.key === "ArrowRight" && classement && ouverte < classement.candidats.length - 1) choisir(ouverte + 1);
    else if (e.key === "ArrowLeft" && ouverte > 0) choisir(ouverte - 1);
  }, true);

  demarrer();
})();
