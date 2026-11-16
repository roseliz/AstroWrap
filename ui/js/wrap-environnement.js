// "But in this area…": what to respect and what to watch out for around an Earth site, the ingredients of the
// wrap on the last card of the AstroWrap (js/bilan.js). Fetched from the browser, public APIs without keys (CORS open):
//   OpenStreetMap / Overpass   protected areas, nature reserves, indigenous lands, military zones (inside + nearby)
//   USGS Earthquake Catalog    M5+ earthquakes within 300 km since 2000
//   NASA EONET v3              natural events tracked by NASA (wildfires, storms, floods, volcanoes…) since 2016
//   Open-Meteo archive         last full year of daily weather (ERA5): extremes, rain, best season, elevation
// Each source has its own timeout; a source that fails only removes its ingredients.
//
// window.environnementSite({ lat, lon, rayonKm, protege }, surCartes) -> Promise<{ cartes, sources, echecs }>
//   carte = { ton: "respect" | "attention" | "calme", icone, titre (2–3 words), valeur (the big number), sous (tiny tag),
//             detail (one sentence, shown on hover), source }

(function () {
  const nb = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  const nb1 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
  const pct = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 0 });
  const MOIS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  const distKm = (a, b, c, d) => {
    const r = Math.PI / 180, h = Math.sin((c - a) * r / 2) ** 2 + Math.cos(a * r) * Math.cos(c * r) * Math.sin((d - b) * r / 2) ** 2;
    return 12742 * Math.asin(Math.min(1, Math.sqrt(h)));
  };
  async function obtenir(url, options = {}, delai = 15000) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), delai);
    try {
      const r = await fetch(url, { ...options, signal: ctrl.signal });
      if (!r.ok) throw new Error(`${r.status}`);
      return await r.json();
    } finally { clearTimeout(t); }
  }

  // ------------------------------------------------------------------ OpenStreetMap (Overpass)
  async function zonesProtegees(lat, lon, rayonKm) {
    const R = Math.round(rayonKm * 1000);
    const ll = `${lat.toFixed(5)},${lon.toFixed(5)}`;
    const q = `[out:json][timeout:25];
is_in(${ll})->.dans;
(area.dans["boundary"~"^(protected_area|national_park|aboriginal_lands)$"];area.dans["leisure"="nature_reserve"];area.dans["landuse"="military"];);
out tags;
(nwr["boundary"~"^(protected_area|national_park|aboriginal_lands)$"](around:${R},${ll});
 nwr["leisure"="nature_reserve"](around:${R},${ll});
 nwr["landuse"="military"](around:${R},${ll});
 nwr["military"="danger_area"](around:${R},${ll}););
out tags 80;`;
    const d = await obtenir("https://overpass-api.de/api/interpreter",
      { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: "data=" + encodeURIComponent(q) }, 15000);
    const vus = new Map();
    (d.elements || []).forEach((e) => {
      const t = e.tags || {};
      const nom = t["name:en"] || t.name || t.official_name;
      if (!nom) return;
      const genre = t.landuse === "military" || t.military ? "militaire"
        : t.boundary === "aboriginal_lands" || t.protect_class === "24" ? "autochtone"
        : t.boundary === "national_park" || t.protect_class === "2" ? "parc" : "protege";
      const cle = nom.toLowerCase();
      if (vus.has(cle)) { if (e.type === "area") vus.get(cle).dedans = true; return; }
      vus.set(cle, { nom, genre, classe: +t.protect_class || null, dedans: e.type === "area" });
    });
    return [...vus.values()];
  }

  function cartesProtegees(zones, rayonKm, protege) {
    const cartes = [];
    const src = "© OpenStreetMap contributors";
    const strict = (z) => z.genre === "parc" || (z.classe && z.classe <= 2);
    const nature = zones.filter((z) => z.genre === "parc" || z.genre === "protege")
      .sort((a, b) => (b.dedans - a.dedans) || (strict(b) - strict(a)));
    const autochtones = zones.filter((z) => z.genre === "autochtone");
    const militaires = zones.filter((z) => z.genre === "militaire");
    if (nature.length) {
      const z = nature[0];
      cartes.push({ ton: "respect", icone: "feuille", titre: z.genre === "parc" ? "National park" : "Protected area",
        valeur: z.dedans ? "Inside" : `${nature.length} near`, sous: z.nom,
        detail: `${z.nom}: ${strict(z) ? "strictly protected, research permits needed, marked tracks only." : "ask the managing authority before any test."}`, source: src });
    } else if (protege && protege.part != null && protege.part >= 0.05) {
      cartes.push({ ton: "respect", icone: "feuille", titre: "Protected", valeur: pct.format(protege.part), sous: "around the site",
        detail: "Part of the site in a protected area (WDPA): permits needed, leave no trace.", source: "UNEP-WCMC & IUCN, Protected Planet" });
    } else {
      cartes.push({ ton: "calme", icone: "feuille", titre: "Protected areas", valeur: "None", sous: `within ${nb.format(rayonKm)} km`,
        detail: "No protected area mapped nearby. Still: leave no trace.", source: src });
    }
    if (autochtones.length) {
      cartes.push({ ton: "respect", icone: "mains", titre: "Indigenous land", valeur: "Ask first", sous: autochtones[0].nom,
        detail: "Ask the community for free, prior and informed consent before any campaign.", source: src });
    }
    if (militaires.length) {
      cartes.push({ ton: "attention", icone: "barriere", titre: "Military zone", valeur: militaires.some((z) => z.dedans) ? "Inside" : `${militaires.length} near`,
        sous: "restricted access", detail: "Restricted access, possible unexploded ordnance: check with the authorities.", source: src });
    }
    return cartes;
  }
  /** Repli quand OpenStreetMap ne répond pas : la part d'aires protégées que le serveur a déjà (WDPA). */
  function cartesWdpa(protege) {
    if (!protege || protege.part == null) return [];
    if (protege.part >= 0.05) return cartesProtegees([], 0, protege);
    return [{ ton: "calme", icone: "feuille", titre: "Protected areas", valeur: "None", sous: "on the site",
      detail: "Outside protected areas (WDPA). Still: leave no trace.", source: "UNEP-WCMC & IUCN, Protected Planet" }];
  }

  // ------------------------------------------------------------------ USGS
  async function seismes(lat, lon) {
    const u = new URL("https://earthquake.usgs.gov/fdsnws/event/1/query");
    Object.entries({ format: "geojson", latitude: lat.toFixed(4), longitude: lon.toFixed(4), maxradiuskm: 300, minmagnitude: 5,
      starttime: "2000-01-01", orderby: "magnitude", limit: 2000 }).forEach(([k, v]) => u.searchParams.set(k, v));
    const d = await obtenir(u);
    const f = d.features || [];
    const src = "USGS Earthquake Catalog";
    if (!f.length) return [{ ton: "calme", icone: "onde", titre: "Earthquakes", valeur: "0", sous: "M5+ · 300 km · since 2000",
      detail: "No M5+ earthquake within 300 km since 2000.", source: src }];
    const fort = f[0].properties;
    const forts = f.filter((x) => x.properties.mag >= 6).length;
    return [{ ton: forts || f.length >= 5 ? "attention" : "calme", icone: "onde", titre: "Earthquakes", valeur: nb.format(f.length),
      sous: `M5+ · up to M${nb1.format(fort.mag)}`,
      detail: `Within 300 km since 2000. Strongest: M${nb1.format(fort.mag)}, ${fort.place || "nearby"} (${new Date(fort.time).getFullYear()}).`, source: src }];
  }

  // ------------------------------------------------------------------ NASA EONET
  const EONET = {
    wildfires: { nom: "Wildfires", icone: "flamme", conseil: "check fire bans, no open flames" },
    severeStorms: { nom: "Storms", icone: "vent", conseil: "avoid the storm season" },
    floods: { nom: "Floods", icone: "eau", conseil: "never camp in dry riverbeds" },
    volcanoes: { nom: "Eruptions", icone: "volcan", conseil: "follow the volcano observatory bulletins" },
    dustHaze: { nom: "Dust storms", icone: "vent", conseil: "protect optics and air filters" },
    landslides: { nom: "Landslides", icone: "onde", conseil: "stay off unstable slopes after rain" },
    tempExtremes: { nom: "Heat / cold waves", icone: "thermo", conseil: "plan for heat or cold waves" },
    drought: { nom: "Droughts", icone: "soleil", conseil: "bring all your water" },
    snow: { nom: "Snow events", icone: "flocon", conseil: "pack for snow" },
    seaLakeIce: { nom: "Ice events", icone: "flocon", conseil: "watch ice conditions" },
  };
  async function evenements(lat, lon) {
    const dLat = 3, dLon = Math.min(20, 3 / Math.max(0.2, Math.cos(lat * Math.PI / 180)));
    const bbox = [lon - dLon, Math.min(89, lat + dLat), lon + dLon, Math.max(-89, lat - dLat)].map((x) => x.toFixed(2)).join(",");
    const fin = new Date().toISOString().slice(0, 10);
    const d = await obtenir(`https://eonet.gsfc.nasa.gov/api/v3/events?status=all&start=2016-01-01&end=${fin}&bbox=${bbox}&limit=500`, {}, 20000);
    const groupes = {};
    (d.events || []).forEach((e) => {
      const cat = (e.categories || [])[0];
      if (!cat || !EONET[cat.id]) return;
      let min = Infinity, date = null;
      (e.geometry || []).forEach((g) => {
        const pts = g.type === "Point" ? [g.coordinates] : (g.coordinates || []).flat(1);
        pts.forEach((p) => { if (Array.isArray(p) && p.length >= 2) min = Math.min(min, distKm(lat, lon, p[1], p[0])); });
        if (!date || g.date > date) date = g.date;
      });
      if (min > 300) return;
      const gr = (groupes[cat.id] = groupes[cat.id] || { n: 0, dernier: null });
      gr.n++;
      if (!gr.dernier || date > gr.dernier.date) gr.dernier = { titre: e.title, date };
    });
    return Object.entries(groupes).sort((a, b) => b[1].n - a[1].n).slice(0, 2).map(([id, g]) => {
      const c = EONET[id];
      return { ton: "attention", icone: c.icone, titre: c.nom, valeur: nb.format(g.n), sous: "seen by NASA since 2016",
        detail: `Within 300 km. Latest: ${g.dernier.titre.replace(/\s+/g, " ")} (${new Date(g.dernier.date).toLocaleDateString("en-US", { month: "short", year: "numeric" })}). Be careful: ${c.conseil}.`,
        source: "NASA EONET" };
    });
  }

  // ------------------------------------------------------------------ Open-Meteo (ERA5)
  async function climat(lat, lon) {
    const an = new Date().getFullYear() - 1;
    const u = `https://archive-api.open-meteo.com/v1/archive?latitude=${lat.toFixed(4)}&longitude=${lon.toFixed(4)}&start_date=${an}-01-01&end_date=${an}-12-31`
      + "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,wind_gusts_10m_max&timezone=auto";
    const d = await obtenir(u, {}, 20000);
    const j = d.daily || {};
    const tmax = (j.temperature_2m_max || []).filter((x) => x != null), tmin = (j.temperature_2m_min || []).filter((x) => x != null);
    if (!tmax.length) return [];
    const src = "Open-Meteo, ERA5 reanalysis";
    const chaud = Math.max(...tmax), froid = Math.min(...tmin);
    const pluie = (j.precipitation_sum || []).reduce((s, x) => s + (x || 0), 0);
    const rafale = Math.max(0, ...(j.wind_gusts_10m_max || []).filter((x) => x != null));
    const cartes = [];
    if (froid <= -10 || chaud < 30) {
      cartes.push({ ton: froid <= -20 ? "attention" : "calme", icone: "flocon", titre: "Coldest night", valeur: `${nb.format(froid)} °C`, sous: `in ${an}`,
        detail: froid <= -20 ? "Frostbite risk, batteries drain fast." : "Coldest temperature of the year.", source: src });
    }
    if (chaud >= 30 || froid > -10) {
      cartes.push({ ton: chaud >= 38 ? "attention" : "calme", icone: "soleil", titre: "Hottest day", valeur: `${nb.format(chaud)} °C`, sous: `in ${an}`,
        detail: chaud >= 38 ? "Carry 5+ L of water per person per day, work at dawn." : "Hottest temperature of the year.", source: src });
    }
    cartes.push({ ton: pluie < 50 ? "attention" : "calme", icone: "eau", titre: "Rain", valeur: `${nb.format(pluie)} mm`, sous: "in a year",
      detail: pluie < 50 ? "Almost no water on site: bring it all." : `Total precipitation in ${an}.`, source: src });
    if (rafale >= 90) {
      cartes.push({ ton: "attention", icone: "vent", titre: "Wind gusts", valeur: `${nb.format(rafale)} km/h`, sous: "max",
        detail: "Anchor tents and instruments.", source: src });
    }
    // la meilleure saison : mois aux moyennes supportables
    const mois = Array.from({ length: 12 }, () => ({ hi: [], lo: [], p: 0 }));
    (j.time || []).forEach((t, k) => {
      const m = +t.slice(5, 7) - 1;
      if (j.temperature_2m_max[k] != null) mois[m].hi.push(j.temperature_2m_max[k]);
      if (j.temperature_2m_min[k] != null) mois[m].lo.push(j.temperature_2m_min[k]);
      mois[m].p += j.precipitation_sum[k] || 0;
    });
    const moy = (a) => a.reduce((s, x) => s + x, 0) / Math.max(1, a.length);
    const bons = mois.map((m) => m.hi.length && moy(m.hi) <= 32 && moy(m.lo) >= -12 && m.p <= 120);
    const nBons = bons.filter(Boolean).length;
    let fenetre;
    if (nBons === 12) fenetre = "All year";
    else if (!nBons) fenetre = "Never easy";
    else {
      const debut = bons.findIndex((b, i) => b && !bons[(i + 11) % 12]);
      let fin = debut;
      while (bons[(fin + 1) % 12] && (fin + 1) % 12 !== debut) fin = (fin + 1) % 12;
      fenetre = debut === fin ? MOIS[debut] : `${MOIS[debut]}–${MOIS[fin]}`;
    }
    cartes.push({ ton: nBons ? "calme" : "attention", icone: "calendrier", titre: "Best time to go", valeur: fenetre, sous: "mild months",
      detail: "Months with mild averages: under 32 °C by day, above −12 °C at night, little rain.", source: src });
    if (d.elevation >= 2500) {
      cartes.push({ ton: "attention", icone: "montagne", titre: "Altitude", valeur: `${nb.format(d.elevation)} m`, sous: "thin air",
        detail: "Acclimatize for a few days, watch for altitude sickness.", source: "Open-Meteo, Copernicus DEM" });
    }
    return cartes;
  }

  /** Lance les quatre sources ; surCartes(cartes) est appelé dès que chacune répond, la promesse finit quand toutes ont fini. */
  window.environnementSite = async function ({ lat, lon, rayonKm = 20, protege = null }, surCartes = () => {}) {
    const ordre = { respect: 0, attention: 1, calme: 2 };
    const taches = [
      ["OpenStreetMap", zonesProtegees(lat, lon, rayonKm).then((z) => cartesProtegees(z, rayonKm, protege), (e) => {
        const repli = cartesWdpa(protege);
        if (!repli.length) throw e;
        return repli;
      })],
      ["NASA EONET", evenements(lat, lon)],
      ["USGS", seismes(lat, lon)],
      ["Open-Meteo", climat(lat, lon)],
    ];
    const cartes = [], echecs = [];
    await Promise.all(taches.map(([nom, p]) => p.then((c) => {
      const nouvelles = c.slice().sort((a, b) => ordre[a.ton] - ordre[b.ton]).slice(0, Math.max(0, 8 - cartes.length));
      cartes.push(...nouvelles);
      if (nouvelles.length) surCartes(nouvelles);
    }, () => { echecs.push(nom); })));
    return { cartes, sources: [...new Set(cartes.map((c) => c.source))], echecs };
  };
})();
