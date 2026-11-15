// Repères : sites connus de Mars et de la Lune, affichés sur le globe 3D et sur la carte 2D.
// Ils servent à se situer avant de peindre une zone ; un clic sur un repère y amène la vue.
//
// Coordonnées planétocentriques, longitude est positive (-180 à 180). Sites d'atterrissage : point
// d'atterrissage publié par la mission. Reliefs : centre approximatif.
// niveau 1 = nom toujours affiché ; niveau 2 = nom affiché quand on zoome (le point reste visible).
//
// Dépend de window.vueCorps (globe-mars.js ou globe-lune.js).

(function () {
  const v = window.vueCorps;
  if (!v) return;

  const REPERES = {
    mars: [
      { nom: "Jezero", lat: 18.44, lng: 77.45, type: "mission", niveau: 1, info: "Perseverance (2021): ancient lake and delta, clays and carbonates." },
      { nom: "Gale", lat: -4.59, lng: 137.44, type: "mission", niveau: 1, info: "Curiosity (2012): lake sediments of Mount Sharp, clays and sulfates." },
      { nom: "Meridiani Planum", lat: -1.95, lng: -5.53, type: "mission", niveau: 1, info: "Opportunity (2004): sulfates and hematite spherules, traces of acidic water." },
      { nom: "Gusev", lat: -14.57, lng: 175.47, type: "mission", niveau: 2, info: "Spirit (2004): basalts, hydrated silica near Home Plate." },
      { nom: "Chryse Planitia", lat: 22.27, lng: -47.95, type: "mission", niveau: 2, info: "Viking 1 (1976)." },
      { nom: "Utopia Planitia", lat: 47.64, lng: 134.29, type: "mission", niveau: 2, info: "Viking 2 (1976): large northern plain, ground ice." },
      { nom: "Ares Vallis", lat: 19.13, lng: -33.22, type: "mission", niveau: 2, info: "Mars Pathfinder and Sojourner (1997): flood plain." },
      { nom: "Vastitas Borealis", lat: 68.22, lng: -125.75, type: "mission", niveau: 2, info: "Phoenix (2008): water ice and perchlorates just below the surface." },
      { nom: "Elysium Planitia", lat: 4.5, lng: 135.62, type: "mission", niveau: 2, info: "InSight (2018): seismology of Mars." },
      { nom: "Zhurong", lat: 25.07, lng: 109.93, type: "mission", niveau: 2, info: "Chinese rover Zhurong (2021), southern Utopia Planitia." },
      { nom: "Olympus Mons", lat: 18.65, lng: -133.8, type: "relief", niveau: 1, info: "Tallest volcano in the Solar System, about 22 km." },
      { nom: "Valles Marineris", lat: -13.9, lng: -59.2, type: "relief", niveau: 1, info: "Canyon system about 4,000 km long." },
      { nom: "Hellas Planitia", lat: -42.4, lng: 70.5, type: "relief", niveau: 1, info: "Impact basin, the lowest point on Mars (about 7 km below the datum)." },
      { nom: "Mawrth Vallis", lat: 22.6, lng: -16.5, type: "relief", niveau: 2, info: "One of the largest clay outcrops on Mars." },
      { nom: "Arcadia Planitia", lat: 47.2, lng: -175.7, type: "relief", niveau: 2, info: "Ice close to the surface, a candidate for a crewed mission." },
    ],
    lune: [
      { nom: "Apollo 11", lat: 0.674, lng: 23.473, type: "mission", niveau: 1, info: "Sea of Tranquility (1969): first human steps, basalts." },
      { nom: "Apollo 12", lat: -3.012, lng: -23.422, type: "mission", niveau: 2, info: "Ocean of Storms (1969)." },
      { nom: "Apollo 14", lat: -3.645, lng: -17.471, type: "mission", niveau: 2, info: "Fra Mauro (1971): impact breccias." },
      { nom: "Apollo 15", lat: 26.132, lng: 3.634, type: "mission", niveau: 1, info: "Hadley-Apennine (1971): rille, mountains, anorthosite (the “Genesis Rock”)." },
      { nom: "Apollo 16", lat: -8.973, lng: 15.5, type: "mission", niveau: 2, info: "Descartes (1972): highlands, breccias." },
      { nom: "Apollo 17", lat: 20.191, lng: 30.772, type: "mission", niveau: 1, info: "Taurus-Littrow (1972): orange volcanic soil, last crewed mission." },
      { nom: "Chang'e 4", lat: -45.444, lng: 177.599, type: "mission", niveau: 1, info: "First landing on the far side (2019), Von Kármán crater." },
      { nom: "Chang'e 5", lat: 43.058, lng: -51.916, type: "mission", niveau: 2, info: "Sample return (2020), near Mons Rümker." },
      { nom: "Chandrayaan-3", lat: -69.373, lng: 32.319, type: "mission", niveau: 2, info: "Vikram lander (2023), the closest to the south pole at the time." },
      { nom: "Shackleton", lat: -89.67, lng: 129.78, type: "relief", niveau: 1, info: "South pole crater; the Artemis candidate regions surround it." },
      { nom: "Tycho", lat: -43.31, lng: -11.36, type: "relief", niveau: 1, info: "Young rayed crater, about 85 km." },
      { nom: "Copernicus", lat: 9.62, lng: -20.08, type: "relief", niveau: 2, info: "Crater with central peaks, about 93 km." },
    ],
  }[v.corps] || [];

  // Altitude de la vue après un clic sur un repère (en rayons du corps).
  const ALTITUDE_ZOOM = v.corps === "lune" ? 0.3 : 0.18;
  const TYPES = { mission: "Landing site", relief: "Landform" };

  function element(r) {
    const el = document.createElement("div");
    el.className = `repere repere-${r.type} niveau-${r.niveau}`;
    el.innerHTML = `<button type="button" class="repere-contenu"><span class="repere-point" aria-hidden="true"></span><span class="repere-nom"></span></button>`;
    el.querySelector(".repere-nom").textContent = r.nom;
    const bouton = el.querySelector("button");
    bouton.title = `${r.nom} (${TYPES[r.type]}): ${r.info}`;
    bouton.setAttribute("aria-label", `${r.nom}, ${TYPES[r.type].toLowerCase()}. ${r.info} Click to go there.`);
    // Le clic ne doit pas faire tourner le globe ni déplacer la carte.
    ["pointerdown", "mousedown", "touchstart", "dblclick"].forEach((ev) => bouton.addEventListener(ev, (e) => e.stopPropagation()));
    bouton.addEventListener("click", (e) => {
      e.stopPropagation();
      v.arreterRotation();
      v.allerA(r.lat, r.lng, ALTITUDE_ZOOM);
    });
    return el;
  }

  // --- globe 3D
  if (v.globe) {
    v.globe
      .htmlElementsData(REPERES)
      .htmlLat("lat")
      .htmlLng("lng")
      .htmlAltitude(0.004)
      .htmlElement(element)
      .htmlTransitionDuration(0)
      // Repère caché quand il passe derrière la planète.
      .htmlElementVisibilityModifier((el, visible) => el.classList.toggle("repere-cache", !visible));
  }

  // --- carte 2D (créée à la demande)
  let couche2D = null;
  function preparer2D() {
    const p = v.plane();
    if (!p || couche2D) return;
    couche2D = L.layerGroup().addTo(p.carte);
    for (const r of REPERES) {
      L.marker([r.lat, r.lng], {
        icon: L.divIcon({ className: "repere-leaflet", html: element(r), iconSize: [0, 0] }),
        keyboard: false,
        interactive: false,   // le bouton à l'intérieur gère le clic
      }).addTo(couche2D);
    }
  }
  document.addEventListener("vue:changee", preparer2D);
  preparer2D();

  // --- noms de niveau 2 affichés seulement quand on zoome
  setInterval(() => {
    let proche;
    if (v.mode() === "carte") {
      const p = v.plane();
      proche = p ? p.carte.getZoom() >= 2.5 : false;
    } else {
      proche = v.globe ? v.globe.pointOfView().altitude < 1.1 : false;
    }
    document.body.classList.toggle("reperes-detailles", proche);
  }, 300);
})();
