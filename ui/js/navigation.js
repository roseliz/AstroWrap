// Navigation bar, at the top of all pages except the animated summary (fullscreen, it has its own close button).
//
//   [logo AstroWrap]          Moon   Mars   Earth •                 How it works   About
//
// - the name links back to home (index.html, the body selection window);
// - Moon and Mars open the page where the area is painted;
// - Earth opens the results of the last compared area (stored in localStorage by analogues.js, forgotten as soon as
//   no area is painted on Mars or the Moon), or otherwise the globe to explore (index.html#terre, without the welcome
//   window); a colored dot indicates that an area is waiting;
// - About (apropos.html) on the right; on mobile, a ☰ button unfolds the links.
// The ?api=… parameter follows from page to page. Loaded early (without defer): the bar is there before the rest.

(function () {
  const CLE = "analogues-derniere-zone";
  const suite = location.search;
  const page = (location.pathname.split("/").pop() || "index.html").replace(/\.html$/, "") || "index";
  const NOMS = { mars: "Mars", moon: "the Moon" };
  const COULEURS = { mars: "#E0794F", moon: "#C9CED6" };

  function lire() {
    try {
      const z = JSON.parse(localStorage.getItem(CLE) || "null");
      return z && /^[0-9a-f]{12}$/.test(z.id) && NOMS[z.body] ? z : null;
    } catch (e) {
      return null;
    }
  }

  /** Memorizes the last compared area ({ body, id, km2 }); called by analogues.js. */
  function memoriser(z) {
    const avant = lire();
    const neuf = avant && avant.id === z.id && avant.body === z.body ? { ...avant, ...z } : z;
    try { localStorage.setItem(CLE, JSON.stringify(neuf)); } catch (e) { /* private browsing */ }
    majTerre();
  }

  /** No area painted any more on this body (mars or moon): forget the last compared area if it was this body's,
   *  and "Earth" opens the globe to explore instead of old results. The area of the other body stays. Called by
   *  selection-zone.js. */
  function oublier(corps) {
    const z = lire();
    if (!z || (corps && z.body !== corps)) return;
    try { localStorage.removeItem(CLE); } catch (e) { /* private browsing */ }
    majTerre();
  }

  const actif = { lune: "lune", mars: "mars", index: "terre", apropos: "apropos", fonctionnement: "fonctionnement" }[page];
  const lien = (cle, href, texte, extra = "") =>
    `<a class="nav-lien" data-cle="${cle}" href="${href}${suite}${extra}" ${cle === actif ? 'aria-current="page"' : ""}>${texte}</a>`;

  const nav = document.createElement("nav");
  nav.className = "nav";
  nav.setAttribute("aria-label", "Main navigation");
  nav.innerHTML = `
    <a class="nav-nom" href="index.html${suite}" title="Home: choose a body">
      <img src="images/astrowrap-wordmark.png" alt="AstroWrap" height="26">
    </a>
    <button type="button" class="nav-menu" aria-expanded="false" aria-controls="nav-liens" aria-label="Menu">
      <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true"><path d="M3 5h14M3 10h14M3 15h14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
    </button>
    <div class="nav-liens" id="nav-liens">
      <div class="nav-astres">
        ${lien("lune", "lune.html", "Moon")}
        ${lien("mars", "mars.html", "Mars")}
        ${lien("terre", "index.html", "Earth", "#terre")}
      </div>
      <div class="nav-outils">
        ${lien("fonctionnement", "fonctionnement.html", "How it works")}
        ${lien("apropos", "apropos.html", "About")}
      </div>
    </div>`;
  document.body.prepend(nav);
  document.body.classList.add("avec-nav", `page-${page}`);

  const bouton = nav.querySelector(".nav-menu");
  bouton.addEventListener("click", () => {
    const ouvert = nav.classList.toggle("ouvert");
    bouton.setAttribute("aria-expanded", String(ouvert));
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && nav.classList.contains("ouvert")) { nav.classList.remove("ouvert"); bouton.setAttribute("aria-expanded", "false"); bouton.focus(); }
  });

  /** The "Earth" link: results of the last area, or the globe to explore. */
  function majTerre() {
    const t = nav.querySelector('[data-cle="terre"]');
    const zone = lire();
    const ici = page === "index" && zone && location.hash.startsWith(`#${zone.body}/${zone.id}`);
    t.href = zone ? `index.html${suite}#${zone.body}/${zone.id}` : `index.html${suite}#terre`;
    t.classList.toggle("avec-zone", !!zone && !ici);
    t.style.setProperty("--point", zone ? COULEURS[zone.body] : "transparent");
    t.title = zone ? `The analogs of your last area ${zone.body === "mars" ? "on Mars" : "on the Moon"}` +
      (zone.km2 ? ` (${new Intl.NumberFormat("en-US").format(zone.km2)} km²)` : "") : "Explore the Earth";
  }
  majTerre();
  window.addEventListener("hashchange", majTerre);
  window.navigation = { memoriser, oublier, derniereZone: lire };
})();
