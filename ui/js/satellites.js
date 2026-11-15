// Satellites around the globes: one per preprocessing module, with the sources of that module for the body shown.
//
// Each satellite in turn "scans" the body: a veil of its color goes down from the North Pole to the South Pole and
// wraps the whole globe, under a beam coming from the satellite. Then they orbit slowly. A click on a satellite
// opens a window: what the module measures on this body, its sources, and what AstroWrap does with them.
//
// - Earth (index.html, MapLibre): scans during the search; once the results are in, each satellite finishes its
//   turn, and we also wait for whatever is asked (the 3D terrain of the wrap) before resting: window.satellites.
// - Mars and the Moon (mars.html, lune.html, globe.gl): no scan of the globe; only the painted area, from above it.
//
// The satellites are buttons laid over the globe, on orbits computed on screen around the disc of the globe
// (center and radius measured at each frame). A satellite behind the globe is hidden. Their size follows the
// globe's, between 14 and 26 px; they disappear when the globe no longer fits on screen, and on the 2D map.

(function () {
  // What the module does with the compared body: the same text for the three bodies.
  const USAGE = {
    topography: "Slope distribution and flat-ground share are compared as they are. Roughness, elevation range and crater density are compared by their level within each world, because Mars and the Moon are much rougher and more cratered than the Earth.",
    geology: "The rock-type shares of your area and of each Earth site are compared as two mixes. On Earth, vegetation and urban areas also feed the filters that set aside places where the ground cannot be seen.",
    thermal: "Day and night ground temperature, the day-night range, the shares of extreme cold and heat, and daylight in the darkest and brightest seasons are compared between your area and each Earth site.",
    wind: "Strong winds (compared with the speed that sets sand moving on each world), dunes, bare ground, dust and dust storms are compared between Mars and the Earth. The Moon has no atmosphere.",
    volatiles: "Surface ice, ground ice and soil water are compared between your area and each Earth site.",
    astro: "The karst share and the density of caves, lava tubes and volcanoes (per 1,000 km²) are compared, each by its level within its own world.",
    impact: "Not a similarity criterion: it never changes how much a site looks like your area. It feeds the Responsible testing tab, the protected-area filter, the low-impact alternatives and the flight footprint.",
  };
  const COULEURS = { topography: "#F2C14E", geology: "#E07A5F", thermal: "#F2545B", wind: "#C9A0DC", volatiles: "#7CC6FE",
    astro: "#3DDC97", impact: "#8B7CF6" };
  const NOMS = { topography: "Terrain", geology: "Rocks", thermal: "Temperature", wind: "Wind and dust", volatiles: "Ice and water",
    astro: "Volcanoes and caves", impact: "Responsible testing" };

  // Sources per body: those of the READMEs of the preprocessing modules.
  const CORPS = {
    earth: { nom: "Earth", modules: {
      topography: ["The shape of the ground at a 500 m scale: slopes, flat ground, roughness, local elevation range and impact craters.",
        [["Copernicus DEM GLO-90 (ESA), 90 m", "elevation, slopes, roughness"], ["Earth Impact Database (PASSC, University of New Brunswick)", "impact craters"]]],
      geology: ["What the ground is made of: the share of each rock type in every cell, and where land is covered by vegetation or cities.",
        [["GLiM, global lithological map (Hartmann and Moosdorf 2012)", "rock types"], ["NASA EMIT L2B and L3 (ISS imaging spectrometer)", "surface minerals (kept, not compared yet)"],
          ["NASA MODIS MCD12C1, land cover", "vegetation and urban areas"]]],
      thermal: ["How hot the ground gets by day, how cold at night, how often it is extreme, and how much daylight each season brings.",
        [["NASA MODIS MOD11C3 and MYD11C3 (Terra, Aqua)", "ground temperature, day and night"], ["NASA MERRA-2 reanalysis", "air temperature, sunshine, clouds"],
          ["Astronomical computation", "daylight share through the year"]]],
      wind: ["Strong winds compared with the speed that sets sand moving, dunes, bare ground, dust in the air and dust storms.",
        [["NASA MERRA-2 (M2TUNXFLX, M2TMNXAER)", "strong winds, air density, dust load"], ["NASA VIIRS Deep Blue (Suomi NPP)", "dust storms"],
          ["NASA MODIS MCD12C1, land cover", "bare ground"], ["World dune map (Gunn 2026, Nature Communications)", "dunes"]]],
      volatiles: ["Ice on the surface, ice in the ground (permafrost), open water and soil moisture.",
        [["ESA CCI Permafrost v5.0", "ground ice"], ["RGI 7.0 glacier outlines (NSIDC) and Natural Earth ice sheets", "surface ice"],
          ["JRC Global Surface Water v1.4", "lakes and rivers"], ["ESA CCI Soil Moisture v09.2", "soil water"]]],
      astro: ["Karst, caves and pits, lava tubes, volcanoes and hot springs: places that could shelter life or a base.",
        [["WOKAM karst map (BGR, IAH, KIT, UNESCO)", "karst rocks, large cave systems"], ["OpenStreetMap and Wikidata", "cave entrances, lava tubes, hot springs"],
          ["Smithsonian Global Volcanism Program", "volcanoes"]]],
      impact: ["What a field campaign would cost the Earth: protected areas, land already transformed by mines, and the nearest airport.",
        [["WDPA, World Database on Protected Areas (UNEP-WCMC and IUCN)", "protected and strictly protected areas"],
          ["Global-scale mining polygons (Maus et al. 2022)", "mines"], ["OurAirports", "nearest airport with scheduled flights"]]],
    } },
    mars: { nom: "Mars", modules: {
      topography: ["The shape of the ground at a 500 m scale: slopes, flat ground, roughness, local elevation range and impact craters.",
        [["MOLA MEGDR (Mars Global Surveyor), USGS global mosaic, 463 m", "elevation, slopes, roughness"],
          ["Robbins and Hynek (2012) crater catalog, ~384,000 craters of 1 km or more", "impact craters"]]],
      geology: ["What the ground is made of: the geological units of Mars, and the minerals seen from orbit.",
        [["USGS global geologic map of Mars, SIM 3292 (Tanaka et al. 2014)", "rock types"],
          ["OMEGA (Mars Express) global maps (Ody et al. 2012)", "olivine, pyroxene, ferric oxides (kept, not compared yet)"]]],
      thermal: ["How hot the ground gets by day, how cold at night, how often it is extreme, and how much daylight each season brings.",
        [["Mars Climate Database v6.2 (LMD, CNES, ESA)", "ground and air temperature, sunlight, infrared"], ["Astronomical computation", "daylight share through the Martian year"]]],
      wind: ["Strong winds compared with the speed that sets sand moving on Mars, dunes, dust in the air and dust storms.",
        [["Mars Climate Database v6.2 (LMD)", "winds, air density, frost"], ["Montabone dust climatology (Martian years 24 to 36)", "dust load, dust storms"],
          ["Mars Global Digital Dune Database (MGD3), USGS", "dunes"]]],
      volatiles: ["Ice on the surface, buried ice and water in the ground.",
        [["SWIM 2.0 (Putzig et al., Planetary Science Institute)", "buried ice at 0 to 1 m, 1 to 5 m and deeper"],
          ["Mars Odyssey Gamma Ray Spectrometer", "water in the soil (% by mass)"], ["Mars Climate Database v6.2 (LMD)", "surface water ice"]]],
      astro: ["Caves and pits, lava tubes, and places where water once altered the rocks.",
        [["Mars Global Cave Candidate Catalog v1 (Cushing, USGS Astrogeology)", "caves, pits, lava tubes"],
          ["Hydrated mineral sites (Carter et al. 2013, OMEGA and CRISM)", "traces of past water"]]],
    } },
    moon: { nom: "the Moon", modules: {
      topography: ["The shape of the ground at a 500 m scale: slopes, flat ground, roughness, local elevation range and impact craters.",
        [["LOLA LDEM (Lunar Reconnaissance Orbiter), USGS global mosaic, 118 m", "elevation, slopes, roughness"],
          ["Robbins (2018) crater catalog, ~1.3 million craters", "impact craters"]]],
      geology: ["What the ground is made of: the geological units of the Moon, and the minerals seen from orbit.",
        [["Unified Geologic Map of the Moon (USGS 2020)", "rock types"],
          ["Olivine, plagioclase and pyroxene abundances (Lucey et al. 2021, Kaguya MI and Diviner)", "minerals (kept, not compared yet)"]]],
      thermal: ["How hot the ground gets in the lunar day, how cold in the night, and how much sunlight each place gets.",
        [["LRO Diviner Global Cumulative Product", "ground temperature by local time"], ["LRO LOLA (near the poles) and astronomical computation", "daylight share"]]],
      volatiles: ["Ice in the permanently shadowed craters near the poles, and hydrogen in the soil.",
        [["Diviner Polar Resource Product (Paige et al. 2010)", "depth of stable ice"], ["Lunar Prospector neutron spectrometer (Feldman et al. 2001)", "hydrogen in the soil"],
          ["Exposed ice detected by M3 (Li et al. 2018; Lemelin et al. 2021)", "surface ice"]]],
      astro: ["Pits and lava tubes: natural shelters for a future base.",
        [["LROC Lunar Pit Atlas (Wagner and Robinson 2021)", "pits"], ["Current Evidence of Lunar Lava Tubes (Losarcos and Dombard 2026)", "lava tube evidence"]]],
    } },
  };

  const reduit = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const rad = (d) => (d * Math.PI) / 180;
  const DUREE_SCAN = 1400;                               // ms per satellite
  const VITESSE_SCAN = 0.55, VITESSE_LENTE = 0.07;       // rad/s along the orbit
  const ORBITES = [[62, -40], [74, -13], [55, 14], [80, 41], [68, 68], [50, 95], [77, 122]];   // inclination, orientation
  const SVG = `<svg viewBox="0 0 32 32" aria-hidden="true">
    <rect x="1" y="12" width="9" height="8" rx="1" fill="currentColor" opacity="0.55"/>
    <rect x="22" y="12" width="9" height="8" rx="1" fill="currentColor" opacity="0.55"/>
    <path d="M10 16h3M19 16h3" stroke="currentColor" stroke-width="1.5"/>
    <rect x="12.5" y="11" width="7" height="10" rx="2" fill="currentColor"/>
    <path d="M16 11V7M14 6.5h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    <circle cx="16" cy="16" r="1.6" fill="#081120"/></svg>`;
  const echapper = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  /** A constellation around a globe.
   *  g: { corps, conteneur, disque() -> {x, y, R} | null, cible(lat) -> {x, y} (edge of the veil facing us),
   *       voile: { pret(), scan(color, lat | null), fond(color, opacity) } } */
  function creer(g) {
    const fiche = CORPS[g.corps];
    const mods = Object.keys(fiche.modules).map((cle) => ({ cle, nom: NOMS[cle], couleur: COULEURS[cle],
      mesure: fiche.modules[cle][0], sources: fiche.modules[cle][1], usage: USAGE[cle] }));
    let mode = "repos", scan = null, vus = new Set(), fond = null, vitesse = VITESSE_LENTE, dernier = 0;
    let attente = null, attenteFinie = true, quandFini = null;
    const contexte = {};

    const couche = document.createElement("div");
    couche.className = "sats";
    const canvas = document.createElement("canvas");
    canvas.className = "sats-orbites";
    canvas.setAttribute("aria-hidden", "true");
    couche.appendChild(canvas);
    const ctx = canvas.getContext("2d");
    const etiquette = document.createElement("span");
    etiquette.className = "sat-etiquette";
    etiquette.hidden = true;
    couche.appendChild(etiquette);
    const astuce = document.createElement("p");
    astuce.className = "sats-astuce";
    astuce.textContent = "Click a satellite to see the data it brings and where it comes from.";
    couche.appendChild(astuce);
    let clique = false, zone = null;
    // the hint stays in one place (top center), fades in once, then leaves: first satellite click, first drag/zoom, or 10 s
    let astuceVue = false, astuceFinie = false;
    const finirAstuce = () => { astuceFinie = true; astuce.classList.remove("montre"); };
    /** Just under the navigation bar when the layer starts under it (Earth page), else 12 px from the top. */
    const placerAstuce = () => {
      const nav = document.querySelector(".nav");
      const dessous = nav ? nav.getBoundingClientRect().bottom - couche.getBoundingClientRect().top : 0;
      astuce.style.top = `${Math.max(12, dessous + 12)}px`;
    };
    window.addEventListener("resize", () => { if (astuceVue && !astuceFinie) placerAstuce(); });
    const sats = mods.map((m, k) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "sat";
      b.style.setProperty("--c", m.couleur);
      b.setAttribute("aria-label", `${m.nom} satellite: what it measures on ${fiche.nom} and its sources`);
      b.title = m.nom;
      b.innerHTML = SVG;
      b.addEventListener("click", (e) => { e.stopPropagation(); clique = true; finirAstuce(); ouvrir(m, b); });
      b.addEventListener("pointerdown", (e) => e.stopPropagation());     // no area painting under a satellite
      couche.appendChild(b);
      return { m, b, a: 1.17 + 0.045 * k, i: rad(ORBITES[k][0]), o: rad(ORBITES[k][1]), th: k * 2.1, sens: k % 2 ? -1 : 1 };
    });
    g.conteneur.appendChild(couche);
    ["pointerdown", "wheel"].forEach((ev) => g.conteneur.addEventListener(ev, () => { if (astuceVue) finirAstuce(); }, { passive: true }));

    function position(s, G) {
      const a = s.a * G.R;
      const x = a * Math.cos(s.th), y = a * Math.sin(s.th) * Math.cos(s.i), z = a * Math.sin(s.th) * Math.sin(s.i);
      const X = x * Math.cos(s.o) - y * Math.sin(s.o), Y = x * Math.sin(s.o) + y * Math.cos(s.o);
      return { x: G.x + X, y: G.y + Y, z: z / a, cache: z < 0 && Math.hypot(X, Y) < G.R * 0.98 };
    }

    function image(t) {
      requestAnimationFrame(image);
      const dt = dernier ? Math.min(0.1, (t - dernier) / 1000) : 0;
      dernier = t;
      if (document.hidden) return;
      g.voile.pret();
      const w = couche.clientWidth, h = couche.clientHeight, dpr = Math.min(2, window.devicePixelRatio || 1);
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      avancerScan(t);
      const G = g.disque();
      const visible = G && G.R < 0.62 * Math.min(w, h) && G.R > 40;
      couche.classList.toggle("cache", !visible);
      if (!visible) return;
      const cibleV = reduit ? 0 : mode === "repos" ? VITESSE_LENTE : VITESSE_SCAN;
      vitesse += (cibleV - vitesse) * Math.min(1, dt * 1.5);
      const taille = Math.max(14, Math.min(26, G.R * 0.075));

      // Area chosen (Mars, Moon) and visible: the satellites gather above it, in an arc, and scan it in turn;
      // otherwise, they follow their orbits.
      let Z = null;
      if (zone && g.ecran) { const e = g.ecran(zone.lat, zone.lng); if (e && e.visible) Z = e; }
      const lissage = 1 - Math.exp(-dt * 3.2);
      const rz = Z ? Math.max(6, Math.min(G.R * 0.45, (zone.rayonKm / g.rayonKm) * G.R)) : 0;
      if (Z) {
        const d = Math.max(rz + taille * 2.6, G.R * 0.42), N = sats.length, ouverture = rad(Math.min(160, 30 * N));
        sats.forEach((s, k) => {
          const a = -ouverture / 2 + ouverture * (N === 1 ? 0.5 : k / (N - 1));
          s.cible = { x: Z.x + d * Math.sin(a), y: Z.y - d * Math.cos(a), z: 1, cache: false };
        });
      }
      const actif = Z ? sats[Math.floor(t / 900) % sats.length] : scan ? sats[scan.k] : null;

      sats.forEach((s, k) => {
        s.th += s.sens * vitesse * dt * (1.15 - 0.04 * k);
        // orbits: faded when the satellites are gathered
        s.trait = (s.trait == null ? 1 : s.trait) + ((Z ? 0 : 1) - (s.trait == null ? 1 : s.trait)) * lissage;
        if (s.trait < 0.02) return;
        ctx.strokeStyle = s.m.couleur;
        ctx.globalAlpha = s.trait * (s === actif && !Z ? 0.55 : mode === "repos" ? 0.07 : 0.12);
        ctx.lineWidth = s === actif && !Z ? 1.5 : 1;
        ctx.beginPath();
        const th0 = s.th;
        let trait = false;
        for (let j = 0; j <= 96; j++) {
          s.th = th0 + (j / 96) * 2 * Math.PI;
          const p = position(s, G);
          if (p.cache) { trait = false; continue; }
          if (trait) ctx.lineTo(p.x, p.y); else { ctx.moveTo(p.x, p.y); trait = true; }
        }
        s.th = th0;
        ctx.stroke();
      });
      ctx.globalAlpha = 1;

      sats.forEach((s) => {
        const orbite = position(s, G), but = Z ? s.cible : orbite;
        if (!s.ecran) s.ecran = { x: but.x, y: but.y };
        s.ecran.x += (but.x - s.ecran.x) * lissage;
        s.ecran.y += (but.y - s.ecran.y) * lissage;
        const loin = Math.hypot(but.x - s.ecran.x, but.y - s.ecran.y) > 4;     // on the way: never hidden
        const cache = !Z && !loin && orbite.cache, echelle = Z ? 1 : 0.85 + 0.2 * orbite.z;
        s.b.style.setProperty("--s", `${taille}px`);
        s.b.style.transform = `translate(${s.ecran.x}px, ${s.ecran.y}px) scale(${s === actif ? echelle * 1.25 : echelle})`;
        s.b.style.opacity = cache ? "0" : !Z && !loin && orbite.z < 0 ? "0.55" : "1";
        s.b.style.pointerEvents = cache ? "none" : "auto";
        s.b.classList.toggle("actif", s === actif);
        s.pos = { x: s.ecran.x, y: s.ecran.y, cache };
      });

      /** Beam from the satellite to a point, `demi` wide at the end. */
      const faisceau = (s, bas, demi, force) => {
        const p = s.pos, dx = bas.x - p.x, dy = bas.y - p.y, L = Math.hypot(dx, dy) || 1;
        const nx = -dy / L, ny = dx / L;
        const grad = ctx.createLinearGradient(p.x, p.y, bas.x, bas.y);
        grad.addColorStop(0, s.m.couleur + (force ? "AA" : "30"));
        grad.addColorStop(1, s.m.couleur + (force ? "10" : "00"));
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
        ctx.lineTo(bas.x + nx * demi, bas.y + ny * demi);
        ctx.lineTo(bas.x - nx * demi, bas.y - ny * demi);
        ctx.closePath();
        ctx.fill();
      };
      if (Z) {
        sats.forEach((s) => { if (s !== actif) faisceau(s, Z, rz, false); });
        faisceau(actif, Z, rz, true);
        const pulse = 0.5 + 0.5 * Math.sin(t / 140);                // the area under the active beam
        ctx.strokeStyle = actif.m.couleur;
        ctx.globalAlpha = 0.5 + 0.4 * pulse;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(Z.x, Z.y, rz * (1.05 + 0.08 * pulse), 0, 2 * Math.PI);
        ctx.stroke();
        ctx.globalAlpha = 1;
      } else if (actif && scan.lat != null && !actif.pos.cache) {
        const bas = g.cible(Math.max(-84, Math.min(84, scan.lat)));
        if (bas) faisceau(actif, bas, G.R * 0.45, true);
      }
      if (actif && !actif.pos.cache && (Z || (scan && scan.lat != null))) {
        etiquette.hidden = false;
        etiquette.textContent = actif.m.nom;
        etiquette.style.setProperty("--c", actif.m.couleur);
        etiquette.style.transform = `translate(${actif.pos.x + taille * 0.8}px, ${actif.pos.y - taille * 0.9}px)`;
      } else {
        etiquette.hidden = true;
      }

      // the first time the satellites show: the hint fades in (fixed place, css/satellites.css)
      if (!astuceVue && !astuceFinie) { astuceVue = true; placerAstuce(); astuce.classList.add("montre"); setTimeout(finirAstuce, 10000); }
    }

    // ---------------------------------------------------------------- scans, one after another
    function lancerScan(k, t) { scan = { k, t0: t, duree: DUREE_SCAN, lat: 85 }; }
    function avancerScan(t) {
      if (mode === "repos" && !scan) {
        if (fond) {                                       // the last veil fades out slowly
          const o = Math.max(0, 0.13 * (1 - (t - fond.t0) / 900));
          g.voile.fond(fond.couleur, o);
          if (o === 0) fond = null;
        }
        return;
      }
      if (!scan) lancerScan(0, t);
      const p = Math.min(1, (t - scan.t0) / scan.duree);
      const e = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
      scan.lat = 85 - 170 * e;
      g.voile.scan(mods[scan.k].couleur, p < 1 ? scan.lat : null);
      if (p < 1) return;
      vus.add(scan.k);
      fond = { t0: t, couleur: mods[scan.k].couleur };    // the full veil stays under the next one
      g.voile.fond(fond.couleur, 0.13);
      if (mode === "fin" && vus.size >= sats.length && attenteFinie) {
        scan = null;
        mode = "repos";
        if (quandFini) { quandFini(); quandFini = null; }
        return;
      }
      lancerScan((scan.k + 1) % sats.length, t);
    }

    // ---------------------------------------------------------------- window of a satellite
    let modale = null, retour = null;
    function ouvrir(m, bouton) {
      if (!modale) {
        modale = document.createElement("div");
        modale.className = "sat-modale";
        modale.hidden = true;
        modale.addEventListener("click", (e) => { if (e.target === modale) fermer(); });
        document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !modale.hidden) { e.stopImmediatePropagation(); fermer(); } }, true);
        document.body.appendChild(modale);
      }
      const actifs = contexte.actifs, poids = contexte.poids || {};
      const total = Object.entries(poids).filter(([k]) => (actifs || []).includes(k)).reduce((a, [, v]) => a + v, 0);
      const etat = m.cle === "impact" || !actifs ? "" : actifs.includes(m.cle)
        ? `<p class="sat-etat oui">Used in this search · weight ${Math.round(100 * (poids[m.cle] || 0) / (total || 1))}%</p>`
        : `<p class="sat-etat non">Not used for this area</p>`;
      modale.innerHTML = `<div class="sat-carte" role="dialog" aria-modal="true" aria-labelledby="sat-titre" style="--c:${m.couleur}">
          <div class="sat-tete"><span class="sat-icone" aria-hidden="true">${SVG}</span>
            <h2 id="sat-titre">${echapper(m.nom)}</h2>
            <button type="button" class="sat-fermer" aria-label="Close">×</button></div>
          ${etat}
          <h3>What it measures on ${echapper(fiche.nom)}</h3><p>${echapper(m.mesure)}</p>
          <h3>Sources</h3>
          <table><thead><tr><th scope="col">Source</th><th scope="col">Used for</th></tr></thead>
            <tbody>${m.sources.map(([s, u]) => `<tr><td>${echapper(s)}</td><td>${echapper(u)}</td></tr>`).join("")}</tbody></table>
          <h3>How AstroWrap uses it</h3><p>${echapper(m.usage)}</p>
        </div>`;
      modale.querySelector(".sat-fermer").addEventListener("click", fermer);
      modale.hidden = false;
      retour = bouton;
      modale.querySelector(".sat-fermer").focus();
    }
    function fermer() {
      modale.hidden = true;
      if (retour) retour.focus({ preventScroll: true });
    }

    requestAnimationFrame(image);
    return {
      /** Scans in a loop, one after another. */
      chercher() {
        if (reduit) return;
        vus = new Set();
        attenteFinie = true;
        mode = "recherche";
      },
      /** Each satellite finishes its turn (and we wait for `attendre`, if given); the promise resolves when at rest. */
      terminer(attendre) {
        if (reduit || mode === "repos") { mode = "repos"; return Promise.resolve(attendre).catch(() => null); }
        if (attendre) {
          attenteFinie = false;
          const moi = (attente = Promise.resolve(attendre).catch(() => null));
          moi.then(() => { if (attente === moi) attenteFinie = true; });
        }
        mode = "fin";
        return new Promise((r) => { quandFini = r; });
      },
      contexte(c) { Object.assign(contexte, c); },
      /** Area chosen ({ lat, lng, rayonKm }): the satellites gather above it; null: back to their orbits. */
      rassembler(z) {
        zone = z;
        if (z) { mode = "repos"; scan = null; g.voile.scan("#000000", null); }
      },
    };
  }

  // ------------------------------------------------------------------ destination on the sphere
  function destination(lat, lon, d, cap) {
    const p = rad(lat), l = rad(lon), c = rad(d), b = rad(cap);
    const p2 = Math.asin(Math.sin(p) * Math.cos(c) + Math.cos(p) * Math.sin(c) * Math.cos(b));
    const l2 = l + Math.atan2(Math.sin(b) * Math.sin(c) * Math.cos(p), Math.cos(c) - Math.sin(p) * Math.sin(p2));
    return [((l2 * 180) / Math.PI + 540) % 360 - 180, (p2 * 180) / Math.PI];
  }

  // ------------------------------------------------------------------ Earth: MapLibre
  function terre() {
    const map = window.carteTerre;
    const vide = { type: "FeatureCollection", features: [] };
    const anneau = (bas) => {
      const haut = 85, a = [];
      for (let lo = -180; lo <= 180; lo += 2) a.push([lo, haut]);
      for (let la = haut; la >= bas; la -= 2) a.push([180, la]);
      a.push([180, bas]);
      for (let lo = 180; lo >= -180; lo -= 2) a.push([lo, bas]);
      for (let la = bas; la <= haut; la += 2) a.push([-180, la]);
      a.push([-180, haut]);
      return { type: "Feature", geometry: { type: "Polygon", coordinates: [a] }, properties: {} };
    };
    const bord = (la) => {
      const l = [];
      for (let lo = -180; lo <= 180; lo += 2) l.push([lo, la]);
      return { type: "Feature", geometry: { type: "LineString", coordinates: l }, properties: {} };
    };
    const pret = () => !!map.getSource("sat-scan");
    return creer({
      corps: "earth",
      conteneur: map.getContainer(),
      disque() {
        const vue = document.querySelector('[data-vue="globe"]');
        if (vue && vue.getAttribute("aria-pressed") === "false") return null;
        // with the perspective, the visible edge of the globe is a little before 90° from the center: look for the farthest
        const c = map.getCenter(), p0 = map.project(c);
        let R = 0;
        for (const d of [72, 78, 84, 89]) {
          for (let k = 0; k < 8; k++) {
            const p = map.project(destination(c.lat, c.lng, d, 45 * k));
            if (Number.isFinite(p.x)) R = Math.max(R, Math.hypot(p.x - p0.x, p.y - p0.y));
          }
        }
        return R > 0 ? { x: p0.x, y: p0.y, R } : null;
      },
      cible: (lat) => map.project([map.getCenter().lng, lat]),
      rayonKm: 6371,
      ecran(lat, lng) {
        const c = map.getCenter(), p = map.project([lng, lat]);
        const cosd = Math.sin(rad(lat)) * Math.sin(rad(c.lat)) + Math.cos(rad(lat)) * Math.cos(rad(c.lat)) * Math.cos(rad(lng - c.lng));
        return { x: p.x, y: p.y, visible: cosd > 0.15 };
      },
      voile: {
        pret() {
          if (pret()) return;
          try {                                           // the style may not be ready: try again at the next frame
            if (!map.getStyle()) return;
            map.addSource("sat-fond", { type: "geojson", data: vide, tolerance: 0 });
            map.addSource("sat-scan", { type: "geojson", data: vide, tolerance: 0 });
            map.addSource("sat-bord", { type: "geojson", data: vide, tolerance: 0 });
            map.addLayer({ id: "sat-fond", type: "fill", source: "sat-fond", paint: { "fill-color": "#FFFFFF", "fill-opacity": 0 } });
            map.addLayer({ id: "sat-scan", type: "fill", source: "sat-scan", paint: { "fill-color": "#FFFFFF", "fill-opacity": 0.2 } });
            map.addLayer({ id: "sat-bord", type: "line", source: "sat-bord",
              paint: { "line-color": "#FFFFFF", "line-width": 2.5, "line-blur": 1.5, "line-opacity": 0.95 } });
          } catch (e) { /* later */ }
        },
        scan(couleur, lat) {
          if (!pret()) return;
          map.setPaintProperty("sat-scan", "fill-color", couleur);
          map.setPaintProperty("sat-bord", "line-color", couleur);
          map.getSource("sat-scan").setData(lat == null ? vide : anneau(lat));
          map.getSource("sat-bord").setData(lat == null ? vide : bord(lat));
        },
        fond(couleur, o) {
          if (!pret()) return;
          map.getSource("sat-fond").setData(o > 0 ? anneau(-85) : vide);
          map.setPaintProperty("sat-fond", "fill-color", couleur);
          map.setPaintProperty("sat-fond", "fill-opacity", o);
        },
      },
    });
  }

  // ------------------------------------------------------------------ Mars and the Moon: globe.gl
  function corpsGlobeGl(V) {
    const globe = V.globe, cam = globe.camera(), r0 = globe.getGlobeRadius();
    // three.js classes taken from the globe itself (globe.gl bundles its own copy, without window.THREE); the globe
    // is only in the scene after a while: look for it at each frame until it is found.
    let Sphere = null;
    const enveloppe = { scan: null, bord: null, fond: null };
    function preparer() {
      if (Sphere) return;
      let surface = null;
      globe.scene().traverse((o) => {
        if (!surface && o.isMesh && o.geometry && o.geometry.type === "SphereGeometry" && o.material && o.material.emissive
          && Math.abs(o.geometry.parameters.radius - r0) < 1e-6) surface = o;
      });
      if (!surface) return;
      const Mesh = surface.constructor, Mat = surface.material.constructor;
      Sphere = surface.geometry.constructor;
      const mat = (o) => new Mat({ color: 0x000000, emissive: 0xffffff, transparent: true, opacity: o, depthWrite: false, shininess: 0 });
      enveloppe.scan = new Mesh(new Sphere(r0 * 1.008, 64, 32, 0, 2 * Math.PI, 0, 0.01), mat(0.15));
      enveloppe.bord = new Mesh(new Sphere(r0 * 1.009, 64, 2, 0, 2 * Math.PI, 0, 0.01), mat(0.9));
      enveloppe.fond = new Mesh(new Sphere(r0 * 1.006, 64, 32), mat(0));
      Object.values(enveloppe).forEach((m) => { m.renderOrder = 5; m.visible = false; globe.scene().add(m); });
    }
    const Vec = cam.position.constructor;
    const rect = () => V.conteneur.getBoundingClientRect();
    return creer({
      corps: ["moon", "lune"].includes(V.corps) ? "moon" : "mars",
      conteneur: V.conteneur,
      disque() {
        if (V.mode && V.mode() === "carte") return null;
        const R = rect(), c = new Vec(0, 0, 0).project(cam);
        const D = cam.position.length();
        if (!(D > r0)) return null;
        const rayon = Math.tan(Math.asin(r0 / D)) / Math.tan(rad(cam.fov / 2)) * (R.height / 2);
        return { x: (c.x + 1) / 2 * R.width, y: (1 - c.y) / 2 * R.height, R: rayon };
      },
      cible(lat) {
        const p = globe.getScreenCoords(lat, globe.pointOfView().lng, 0.01);
        return p && Number.isFinite(p.x) ? p : null;
      },
      rayonKm: V.rayonKm,
      /** Point (lat, lng) on screen, and whether it is on the visible side (beyond the horizon: hidden). */
      ecran(lat, lng) {
        const p = globe.getScreenCoords(lat, lng, 0), c = globe.getCoords(lat, lng, 0), o = cam.position;
        if (!p || !Number.isFinite(p.x)) return null;
        const D = o.length(), cosd = (c.x * o.x + c.y * o.y + c.z * o.z) / (Math.hypot(c.x, c.y, c.z) * D);
        return { x: p.x, y: p.y, visible: cosd > r0 / D + 0.05 };
      },
      voile: {
        pret: preparer,
        scan(couleur, lat) {
          if (!enveloppe.scan) return;
          if (lat == null) { enveloppe.scan.visible = enveloppe.bord.visible = false; return; }
          const theta = Math.max(0.01, rad(90 - lat));
          enveloppe.scan.geometry.dispose();
          enveloppe.scan.geometry = new Sphere(r0 * 1.008, 64, 32, 0, 2 * Math.PI, 0, theta);
          enveloppe.bord.geometry.dispose();
          enveloppe.bord.geometry = new Sphere(r0 * 1.009, 64, 2, 0, 2 * Math.PI, Math.max(0, theta - 0.025), 0.025);
          enveloppe.scan.material.emissive.set(couleur);
          enveloppe.bord.material.emissive.set(couleur);
          enveloppe.scan.visible = enveloppe.bord.visible = true;
        },
        fond(couleur, o) {
          if (!enveloppe.fond) return;
          enveloppe.fond.material.emissive.set(couleur);
          enveloppe.fond.material.opacity = o * 0.8;
          enveloppe.fond.visible = o > 0;
        },
      },
    });
  }

  // ------------------------------------------------------------------ start
  let instanceTerre = null;
  const surTerre = () => (instanceTerre = instanceTerre || (window.carteTerre ? terre() : null));
  window.satellites = {
    chercher() { const s = surTerre(); if (s) s.chercher(); },
    terminer(attendre) { return instanceTerre ? instanceTerre.terminer(attendre) : Promise.resolve(); },
    contexte(c) { const s = surTerre(); if (s) s.contexte(c); },
  };
  // Mars and Moon pages: no scan of the whole globe; the satellites orbit slowly, and only scan the painted area,
  // gathered above it
  const V = window.vueCorps;
  if (V && V.globe && !window.carteTerre) {
    const s = corpsGlobeGl(V);
    // painted area: the satellites come above it
    const suivre = (n, centre, surface) => s.rassembler(n && centre ? { lat: centre[0], lng: centre[1], rayonKm: Math.sqrt(surface / Math.PI) } : null);
    document.addEventListener("zone:changee", (e) => suivre(e.detail.tuiles, e.detail.centre, e.detail.surfaceKm2));
    const Z = window.selectionZone;
    if (Z && Z.centre) suivre(Z.tuiles().length, Z.centre(), Z.surfaceKm2());
  }
})();
