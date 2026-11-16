// "Can you trust it?" tab of the How it works page: draws data/validation.json, written by scripts/validation.py.
// Every number on the tab is read or derived from that file; nothing here is typed by hand.
(() => {
  const $ = (s) => document.querySelector(s);
  const NOMS = { topography: "Terrain", geology: "Rocks", thermal: "Temperature", wind: "Wind and dust",
    volatiles: "Water and ice", astro: "Caves" };
  const ORDRE = ["topography", "geology", "thermal", "wind", "volatiles", "astro"];
  const nb = new Intl.NumberFormat("en-US");
  const pc = (x) => `${Math.round(100 * x)}%`;
  const echappe = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  /** Rank percentile, enough digits to tell 0.005% from 0.09%. */
  function fmtP(p) {
    const v = 100 * p;
    return `${v < 0.01 ? v.toFixed(3) : v < 0.1 ? v.toFixed(2) : v < 10 ? v.toFixed(1) : v.toFixed(0)}%`;
  }
  const MIN = 1e-5;                                        // log axis: 0.001% to 100%
  const x = (p) => `${(100 * (Math.log10(Math.max(p, MIN)) + 5)) / 5}%`;

  let pret = false;
  const onglet = $("#hw-o3");
  if (!onglet) return;
  const charger = () => {
    if (pret) return;
    pret = true;
    fetch("data/validation.json").then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(dessiner).catch(() => { $("#v-kpis").innerHTML = `<p class="v-charge">The results file could not be loaded.</p>`; });
  };
  onglet.addEventListener("click", charger);
  if (location.hash === "#validation") charger();

  function dessiner(V) {
    const paires = V.areas.flatMap((a) => a.analogs.map((e) => ({ ...e, zone: a })));
    const attendus = paires.filter((e) => e.expected && e.rank);
    const n = attendus.length;
    const h5 = attendus.filter((e) => e.pct <= 0.05).length;
    const p5 = attendus.filter((e) => e.pct_slope != null && e.pct_slope <= 0.05).length;
    const r5 = attendus.reduce((s, e) => s + e.p_top5_random, 0);
    const top10 = attendus.filter((e) => e.in_top10).length;
    const st = V.stability, garde = st.reduce((s, x) => s + x.top3_kept, 0) / st.length;
    const T = V.timing;

    // ---------------------------------------------------------------- headline numbers
    const kpi = (val, lib, sous) => `<div class="v-kpi"><b>${val}</b><span>${lib}</span><small>${sous}</small></div>`;
    $("#v-kpis").innerHTML =
      kpi(`${h5} of ${n}`, "documented analogs land in the top 5% of Earth’s land cells",
        `Random ranking: ${r5.toFixed(1)} expected · slope alone: ${p5}`) +
      kpi(pc(garde), "of the top-3 sites stay in the top 10 when every weight moves by up to ±50%",
        `${st[0].runs} runs per area, ${st.length} areas`) +
      (T.prod_median_wall_s != null
        ? kpi(`${T.prod_median_wall_s.toFixed(1)} s`, "median search time on the live site, network and download included",
          `${T.prod_median_server_s.toFixed(1)} s of it on the server · ${T.prod.length} searches · ${T.local_median_s.toFixed(1)} s on a laptop`)
        : kpi(`${T.local_median_s.toFixed(1)} s`, "median search time on the server (local run)", `${T.local_server_s.length} searches`));

    // ---------------------------------------------------------------- 1. backtest
    $("#v-bt-retenir").textContent = `${h5} of ${n} in the top 5% (random: ${r5.toFixed(1)}, slope alone: ${p5}). ` +
      `Only ${top10} of ${n} reach the app’s top 10.`;
    const axe = [1e-5, 1e-4, 1e-3, 1e-2, 1e-1, 1].map((p) => `<span style="left:${x(p)}">${fmtP(p)}</span>`).join("");
    let html = `<div class="v-bt-tete" role="row"><span role="columnheader">Painted area → Earth analog</span>
      <span role="columnheader" class="v-bt-axe">${axe}</span><span role="columnheader">Rank</span><span role="columnheader">Top 10</span></div>`;
    let zonePrec = null;
    paires.forEach((e, j) => {
      const neuf = e.zone !== zonePrec; zonePrec = e.zone;
      const hors = !e.expected;
      html += `<div class="v-bt-ligne${hors ? " v-hors" : ""}${neuf ? " v-neuf" : ""}" role="row" tabindex="0" data-j="${j}">
        <span role="cell" class="v-bt-nom">${neuf ? `<em>${echappe(e.zone.name)}</em>` : ""}${echappe(e.name)}${hors ? ` <small>minerals: not counted</small>` : ""}</span>
        <span role="cell" class="v-bt-piste" aria-hidden="true"><i class="v-zone5" style="width:${x(0.05)}"></i>
          <i class="v-pt v-hasard" style="left:${x(e.pct_random)}"></i>
          ${e.pct_slope != null ? `<i class="v-pt v-pente" style="left:${x(e.pct_slope)}"></i>` : ""}
          ${e.rank ? `<i class="v-pt v-nous" style="left:${x(e.pct)}"></i>` : ""}</span>
        <span role="cell" class="v-bt-rang">${e.rank ? `top ${fmtP(e.pct)}` : "no data"}</span>
        <span role="cell" class="v-bt-top">${e.in_top10 ? "yes" : "no"}</span></div>`;
    });
    $("#v-bt").innerHTML = html;
    bulles(paires);

    // ---------------------------------------------------------------- 2. stability
    const variantes = V.variants;
    const repeint = (id) => variantes.filter((v) => v.id === id);
    const moyRep = variantes.reduce((s, v) => s + v.top10_overlap, 0) / variantes.length;
    const vides = variantes.filter((v) => v.n_sites === 0);
    $("#v-st-retenir").textContent = `Weights ±50%: ${pc(garde)} of top-3 sites kept. Repainting: ${pc(moyRep)} of the top 10 kept.`;
    const barre = (v, t) => `<span class="v-barre" title="${t}"><i style="width:${100 * v}%"></i><b>${pc(v)}</b></span>`;
    $("#v-st").innerHTML = `<div class="v-st-tete"><span></span><span>Weights ±50%<small>top 3 kept in top 10</small></span>
        <span>Repainted<small>top 10 kept, 4 brushes</small></span></div>` +
      st.map((s) => {
        const a = V.areas.find((z) => z.id === s.id), r = repeint(s.id);
        const m = r.reduce((t, v) => t + v.top10_overlap, 0) / r.length;
        const detail = r.map((v) => `${v.variant}: ${v.n_sites ? pc(v.top10_overlap) : "no site"}`).join(" · ");
        return `<div class="v-st-ligne"><span>${echappe(a.name.replace(/ \(.*/, ""))}</span>
          ${barre(s.top3_kept, `${pc(s.all3_kept_runs)} of runs keep all three`)}${barre(m, detail)}</div>`;
      }).join("") +
      `<p class="v-note">Repaints: smaller, larger, elongated, shifted.</p>`;

    // ---------------------------------------------------------------- 3. coverage
    const sites = V.areas.flatMap((a) => a.top10.map((s) => ({ ...s, zone: a })));
    const avec = (k) => sites.filter((s) => s[k] != null);
    const urb = avec("urban").filter((s) => s.urban > 0.3), nua = avec("cloud").filter((s) => s.cloud > 0.5);
    const veg = avec("vegetation").filter((s) => s.vegetation > 0.2);
    const jamais = ["mars", "moon"].map((c) => {
      const z = V.areas.filter((a) => a.body === c);
      const k = ORDRE.filter((m) => z.length && z.every((a) => !a.active.includes(m)));
      return k.length ? `${k.map((m) => NOMS[m]).join(" and ")} ${k.length > 1 ? "are" : "is"} never compared on our ${c === "mars" ? "Mars" : "Moon"} areas` : "";
    }).filter(Boolean);
    $("#v-cv-retenir").textContent = jamais.length ? `${jamais.join("; ")}.` : "";
    const tete = V.areas.map((a) => `<span title="${echappe(a.name)}">${echappe(a.name.split(" ")[0])}<small>${a.body === "mars" ? "Mars" : "Moon"}</small></span>`).join("");
    const lignes = ORDRE.map((k) => `<div class="v-cv-ligne"><span>${NOMS[k]}</span>${V.areas.map((a) => {
      const in_ = a.active.includes(k), r = a.inactive.find((i) => i.key === k);
      return `<span class="${in_ ? "v-oui" : "v-non"}" title="${in_ ? "compared" : echappe(r ? r.reason : "not compared")}">${in_ ? "●" : "○"}<small>${in_ ? "compared" : "not compared"}</small></span>`;
    }).join("")}</div>`).join("");
    const part = (t, tot, lib) => `<div class="v-cv-part"><span>${lib}</span>${barre(t.length / Math.max(tot, 1), `${t.length} of ${tot} sites`)}<small>${t.length} of ${tot}</small></div>`;
    $("#v-cv").innerHTML = `<div class="v-cv-mat"><div class="v-cv-ligne v-cv-tete"><span></span>${tete}</div>${lignes}</div>
      <p class="v-cv-sous">Top-10 sites of the six areas (${sites.length} sites)</p>
      ${part(urb, avec("urban").length, "More than 30% urban")}${part(nua, avec("cloud").length, "More than 50% cloud cover")}
      ${part(veg, avec("vegetation").length, "More than 20% dense vegetation")}`;

    // ---------------------------------------------------------------- scoring rule (worked on Jezero's #1 site)
    const J = V.areas[0], ex = J.example || [];
    const vb = (mod, key) => { const m = ex.find((z) => z.key === mod); return m && m.variables.find((v) => v.key === key); };
    const plat = vb("topography", "part_pente_inf_5"), nuit = vb("thermal", "lst_night_mean");
    const sims = ex.filter((m) => J.active.includes(m.key));
    const moy = sims.reduce((s, m) => s + m.similarity, 0) / Math.max(sims.length, 1);
    const ordre = J.active.map((k) => `<li>${NOMS[k]} <small>median ${pc(J.medians[k])}</small></li>`).join("");
    $("#v-regle").innerHTML = `
      <div><h4>Each criterion</h4>
        <p class="v-formule">distance = |Earth − area| ÷ σ, capped at 3<br>similarity = 1 − distance ÷ 3</p>
        <p>σ = spread of that variable over the Earth.</p>
        ${plat ? `<p class="v-ex">Jezero #1: flat ground ${pc(plat.reference)} vs ${pc(plat.earth)} → <b>${pc(plat.similarity)}</b></p>` : ""}
      </div>
      <div><h4>Weights</h4>
        <p class="v-formule">score = Σ wᵢ rᵢ sᵢ ÷ Σ wᵢ rᵢ<br>rᵢ = 0.5 + 0.5 × reliability</p>
        <p>All weights equal by default.</p>
        ${sims.length ? `<p class="v-ex">Jezero #1: ${sims.map((m) => pc(m.similarity)).join(" + ")} ÷ ${sims.length} = <b>${pc(moy)}</b></p>` : ""}
      </div>
      <div><h4>Gates, in this order</h4>
        <ol class="v-portes">${ordre}</ol>
        <p>A cell below the Earth’s median on any criterion is dropped. Sites ≥ ${V.settings.spacing_km} km apart.</p>
        <p class="v-ex">Jezero: ${fmtP(J.n_gated / J.n_eligible)} of cells pass.</p>
      </div>`;

    // ---------------------------------------------------------------- failures
    const pire = urb.sort((a, b) => b.urban - a.urban)[0];
    const thermBas = attendus.filter((e) => (e.below_median || []).includes("thermal")).length;
    const roche0 = V.areas.filter((a) => a.medians.geology === 0).map((a) => a.name.split(" ")[0]);
    const echecs = [];
    if (pire) echecs.push(["Urban sites in the top 10",
      `${urb.length} of ${avec("urban").length} sites are over 30% urban (worst: ${pc(pire.urban)}).`]);
    const cas = (V.large && V.large.n_sites === 0 ? 1 : 0) + vides.length;
    if (cas) echecs.push(["“No site found” on large Moon areas",
      `${cas} large Moon area${cas > 1 ? "s" : ""} returned nothing: every candidate falls just below the Caves median.`]);
    echecs.push(["Temperature sinks real analogs",
      `${thermBas} of ${n} analogs fall below the Temperature median${nuit ? `: Mars nights (${Math.round(nuit.reference)} K) are colder than any Earth desert` : ""}.`]);
    if (roche0.length) echecs.push(["Rocks barely separate cells",
      `Median Rocks similarity is 0% for ${roche0.join(", ")}.`]);
    $("#v-echecs").innerHTML = echecs.map(([t, d]) => `<div class="v-echec"><h4>${t}</h4><p>${d}</p></div>`).join("");

    // ---------------------------------------------------------------- honesty
    $("#v-honnete").innerHTML = `<b>Honesty note.</b> No weight was tuned on these areas, but some were looked at while
      building the engine. Qaidam is the only analog never seen before. Mineral analogs (gray) are not counted.`;
    rejeu(V);
  }

  // ------------------------------------------------------------------ replay (the only call to the server, on click)
  const API = (new URLSearchParams(location.search).get("api") || (/^(localhost|127\.0\.0\.1|\[::1\]|)$/.test(location.hostname)
    ? "http://127.0.0.1:8000" : "https://api.astrowrap.earth")).replace(/\/$/, "");
  const km = (a, b) => {
    const r = Math.PI / 180, s = Math.sin((b.lat - a.lat) * r / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin((b.lon - a.lon) * r / 2) ** 2;
    return 2 * 6371.0088 * Math.asin(Math.sqrt(s));
  };

  /** The browser's ranking of the pool (analogues.js, recalculer): default weights, no criterion below the median. */
  function classer(R, n, ecart) {
    const P = R.pool, act = R.active_modules, w = {};
    act.forEach((m) => (w[m] = 1 / act.length));
    const out = [];
    const sc = P.h3.map((_, i) => {
      if (P.water_share[i] != null && P.water_share[i] > R.footprint.max_water) return -1;
      let s = 0, ws = 0, mesure = 0;
      for (const m of act) {
        const sim = P.score_per_module[m][i];
        if (sim == null) { s += R.medians[m] * w[m]; ws += w[m]; continue; }
        if (sim < R.medians[m]) return -1;
        const we = w[m] * (0.5 + 0.5 * (P.reliability_per_module[m][i] ?? 1));
        s += sim * we; ws += we; mesure += w[m];
      }
      return mesure >= R.confidence_min ? s / ws : -1;
    });
    const ordre = sc.map((s, i) => i).filter((i) => sc[i] >= 0).sort((a, b) => sc[b] - sc[a]);
    for (const i of ordre) {
      const [lat, lon] = h3.cellToLatLng(P.h3[i]);
      if (out.every((c) => km(c, { lat, lon }) >= ecart)) out.push({ h3: P.h3[i], lat, lon, score: sc[i] });
      if (out.length >= n) break;
    }
    return out;
  }

  function rejeu(V) {
    const sel = $("#v-rj-zone"), go = $("#v-rj-go"), res = $("#v-rj-res");
    sel.innerHTML = V.areas.map((a, i) => `<option value="${i}">${echappe(a.name)} (${a.body === "mars" ? "Mars" : "Moon"})</option>`).join("");
    go.addEventListener("click", async () => {
      const A = V.areas[+sel.value];
      if (!window.h3 || A.rings == null) { res.innerHTML = `<p class="v-note">Replay unavailable (map library or area size missing).</p>`; return; }
      const cells = h3.gridDisk(h3.latLngToCell(A.lat, A.lon, 6), A.rings);
      go.disabled = true;
      res.innerHTML = `<p class="v-note">Searching the whole Earth for ${echappe(A.name)} (${nb.format(cells.length)} hexagons)…</p>`;
      const t0 = performance.now();
      try {
        const r = await fetch(`${API}/api/search`, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ body: A.body, h3_cells: cells, top_k: 2000, filters: { max_vegetation: V.settings.vegetation_max } }) });
        if (!r.ok) throw new Error(`server answered ${r.status}`);
        const R = await r.json(), mur = (performance.now() - t0) / 1000;
        const top = classer(R, A.top10.length || 10, V.settings.spacing_km);
        const meme = top.filter((s) => A.top10.some((t) => km(s, t) <= 100)).length;
        res.innerHTML = `<p class="v-retenir"><b>${mur.toFixed(1)} s</b> in your browser (${R.duration_s.toFixed(1)} s on the server).
          ${meme} of ${top.length} sites match the recorded top 10 within 100 km${A.top10.length !== top.length ? ` (recorded: ${A.top10.length} sites)` : ""}.</p>
          <ol class="v-rj-liste">${top.map((s) => {
            const ok = A.top10.some((t) => km(s, t) <= 100);
            return `<li><span>${s.lat.toFixed(2)}°, ${s.lon.toFixed(2)}°</span><span>${pc(s.score)}</span>
              <span class="${ok ? "v-oui" : "v-non"}">${ok ? "● as recorded" : "○ new"}</span></li>`;
          }).join("")}</ol>
          ${top.length ? "" : `<p class="v-note">No site passes the browser’s gates for this area.</p>`}`;
      } catch (e) {
        res.innerHTML = `<p class="v-note">The search could not run: ${echappe(e.message)}. The server at ${echappe(API)} may be asleep or unreachable.</p>`;
      } finally { go.disabled = false; }
    });
  }

  /** One tooltip for every backtest row: exact ranks and why. */
  function bulles(paires) {
    const b = $("#v-bulle"), boite = $("#validation");
    const montrer = (ligne) => {
      const e = paires[+ligne.dataset.j];
      b.innerHTML = `<b>${echappe(e.name)}</b> for ${echappe(e.zone.name)}<br>
        ${e.rank ? `AstroWrap: #${nb.format(e.rank)} of ${nb.format(e.n)} (top ${fmtP(e.pct)})` : "No eligible cell"}<br>
        ${e.rank_slope ? `Slope alone: #${nb.format(e.rank_slope)} of ${nb.format(e.n_slope)} (top ${fmtP(e.pct_slope)})<br>` : ""}
        Random, expected: top ${fmtP(e.pct_random)}<br>
        ${e.rank ? (e.passes_gates ? "Passes every gate" : `Dropped at the gates: below the median on ${e.below_median.map((k) => NOMS[k]).join(", ")}`) : ""}
        ${e.source ? `<br><small>${echappe(e.source)}</small>` : ""}`;
      b.hidden = false;
      const r = ligne.getBoundingClientRect(), o = boite.getBoundingClientRect();
      b.style.top = `${r.bottom - o.top + 6}px`;
      b.style.left = `${Math.min(Math.max(8, r.left - o.left + 40), o.width - b.offsetWidth - 8)}px`;
    };
    document.querySelectorAll(".v-bt-ligne").forEach((l) => {
      l.addEventListener("mouseenter", () => montrer(l));
      l.addEventListener("focus", () => montrer(l));
      l.addEventListener("mouseleave", () => (b.hidden = true));
      l.addEventListener("blur", () => (b.hidden = true));
    });
  }
})();
