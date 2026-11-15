// Home screen: the Moon and Mars appear in 3D at the center of the screen, each within its own frame, rotating on its axis.
// Clicking a celestial body opens its page (lune.html, mars.html) to paint the reference region.
//
// Opened by js/analogues.js when index.html loads without a selected region (#mars/<id>). three.js (r147) is loaded from
// node_modules (npm install) or unpkg; without WebGL, each celestial body is displayed as a scrolling image inside a disk.
// Textures: textures/accueil.js (reduced versions of those used on the Mars and Moon pages).

(function () {
  const ASTRES = [
    { cle: "lune", nom: "The Moon", page: "lune.html", texture: () => window.TEXTURE_ACCUEIL_LUNE,
      info: "No atmosphere · 1/6 of Earth's gravity", inclinaison: 6.7, halo: null },
    { cle: "mars", nom: "Mars", page: "mars.html", texture: () => window.TEXTURE_ACCUEIL_MARS,
      info: "Thin atmosphere · 3/8 of Earth's gravity", inclinaison: 25.2, halo: [1.0, 0.55, 0.35] },
  ];
  const VITESSE = 0.22;                     // rad/s ; quatre fois plus au survol
  const lent = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  let ouvert = null;

  function ouvrir({ surFermeture } = {}) {
    if (ouvert) return;
    const suite = location.search;          // garde ?api=… d'une page à l'autre
    const el = document.createElement("div");
    el.className = "accueil";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "true");
    el.setAttribute("aria-labelledby", "accueil-titre");
    el.innerHTML = `
      <div class="accueil-carte">
        <img class="accueil-logo" src="images/astrowrap-wordmark.png" alt="AstroWrap" height="44">
        <p class="accueil-sur">NASA Space Apps Challenge 2026</p>
        <h2 id="accueil-titre">Where do you want to go?</h2>
        <p class="accueil-texte">Choose a body and paint an area on it: we will find the places on Earth that look most like it.</p>
        <div class="accueil-astres">
          ${ASTRES.map((a) => `
            <a class="astre astre-${a.cle}" href="${a.page}${suite}" data-cle="${a.cle}">
              <span class="astre-cadre"><canvas aria-hidden="true"></canvas></span>
              <span class="astre-nom">${a.nom}</span>
              <span class="astre-info">${a.info}</span>
            </a>`).join("")}
        </div>
        <button type="button" class="accueil-terre">or explore the Earth first</button>
      </div>`;
    document.body.appendChild(el);
    document.body.classList.add("accueil-ouvert");
    const etat = { el, scenes: [], arret: false, surFermeture };
    ouvert = etat;

    el.querySelector(".accueil-terre").addEventListener("click", fermer);
    el.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { e.preventDefault(); fermer(); }
      if (e.key === "Tab") garderFocus(e, el);
    });
    // Le focus va à la fenêtre, pas à un astre (qui paraîtrait déjà choisi) ; Tab passe ensuite aux astres
    el.tabIndex = -1;
    el.focus({ preventScroll: true });

    const T = window.THREE;
    el.querySelectorAll(".astre").forEach((lien, i) => {
      const astre = ASTRES[i];
      const scene = T ? scene3D(lien.querySelector("canvas"), astre) : null;
      if (!scene) {                         // pas de three.js ou pas de WebGL : disque d'image qui défile
        const cadre = lien.querySelector(".astre-cadre");
        cadre.classList.add("astre-plat");
        cadre.style.backgroundImage = `url("${astre.texture()}")`;
        lien.querySelector("canvas").remove();
        return;
      }
      lien.addEventListener("pointerenter", () => { scene.vite = true; });
      lien.addEventListener("pointerleave", () => { scene.vite = false; });
      lien.addEventListener("focus", () => { scene.vite = true; });
      lien.addEventListener("blur", () => { scene.vite = false; });
      etat.scenes.push(scene);
    });
    if (etat.scenes.length) animer(etat);
    window.addEventListener("resize", etat.redim = () => etat.scenes.forEach(dimensionner));
  }

  function fermer() {
    const etat = ouvert;
    if (!etat) return;
    etat.arret = true;
    etat.scenes.forEach((s) => {
      s.scene.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) { if (o.material.map) o.material.map.dispose(); o.material.dispose(); } });
      s.renderer.dispose();
      s.renderer.forceContextLoss();
    });
    window.removeEventListener("resize", etat.redim);
    etat.el.classList.add("accueil-sortie");
    setTimeout(() => etat.el.remove(), 250);
    document.body.classList.remove("accueil-ouvert");
    ouvert = null;
    if (etat.surFermeture) etat.surFermeture();
  }

  /** Tab reste dans la fenêtre d'accueil. */
  function garderFocus(e, el) {
    const f = [...el.querySelectorAll("a, button")];
    const i = f.indexOf(document.activeElement);
    if (i < 0) { e.preventDefault(); (e.shiftKey ? f[f.length - 1] : f[0]).focus(); return; }
    if (e.shiftKey && i <= 0) { e.preventDefault(); f[f.length - 1].focus(); }
    else if (!e.shiftKey && i === f.length - 1) { e.preventDefault(); f[0].focus(); }
  }

  function scene3D(canvas, astre) {
    const T = window.THREE;
    let renderer;
    try {
      renderer = new T.WebGLRenderer({ canvas, antialias: true, alpha: true });
    } catch (e) {
      return null;
    }
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.outputEncoding = T.sRGBEncoding;
    const scene = new T.Scene();
    const camera = new T.PerspectiveCamera(30, 1, 0.1, 20);
    camera.position.set(0, 0, 4.4);

    scene.add(new T.AmbientLight(0xffffff, 0.12));
    const soleil = new T.DirectionalLight(0xffffff, 1.35);
    soleil.position.set(-3, 1.2, 2.4);              // éclairé de côté : on voit le terminateur
    scene.add(soleil);

    const axe = new T.Group();
    axe.rotation.z = (astre.inclinaison * Math.PI) / 180;
    scene.add(axe);
    const texture = new T.TextureLoader().load(astre.texture(), () => renderer.render(scene, camera));
    texture.encoding = T.sRGBEncoding;
    texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
    const corps = new T.Mesh(new T.SphereGeometry(1, 96, 64), new T.MeshStandardMaterial({ map: texture, roughness: 1, metalness: 0 }));
    axe.add(corps);

    if (astre.halo) {                               // atmosphère : un liseré lumineux au bord du disque
      const halo = new T.Mesh(new T.SphereGeometry(1.06, 64, 48), new T.ShaderMaterial({
        uniforms: { couleur: { value: new T.Vector3(...astre.halo) } },
        vertexShader: "varying vec3 vN; void main() { vN = normalize(normalMatrix * normal); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
        fragmentShader: "uniform vec3 couleur; varying vec3 vN; void main() { float i = pow(max(0.0, 0.72 - dot(vN, vec3(0.0, 0.0, 1.0))), 2.2); gl_FragColor = vec4(couleur, 1.0) * i; }",
        side: T.BackSide, blending: T.AdditiveBlending, transparent: true, depthWrite: false,
      }));
      scene.add(halo);
    }
    const s = { renderer, scene, camera, corps, canvas, vite: false, angle: Math.random() * Math.PI * 2 };
    dimensionner(s);
    return s;
  }

  function dimensionner(s) {
    const w = s.canvas.clientWidth || 200, h = s.canvas.clientHeight || 200;
    s.renderer.setSize(w, h, false);
    s.camera.aspect = w / h;
    s.camera.updateProjectionMatrix();
  }

  function animer(etat) {
    let avant = performance.now();
    const pas = (t) => {
      if (etat.arret) return;
      const dt = Math.min(0.1, (t - avant) / 1000);
      avant = t;
      if (!document.hidden) {
        etat.scenes.forEach((s) => {
          s.angle += dt * VITESSE * (lent ? 0.3 : 1) * (s.vite ? 4 : 1);
          s.corps.rotation.y = s.angle;
          s.renderer.render(s.scene, s.camera);
        });
      }
      requestAnimationFrame(pas);
    };
    requestAnimationFrame(pas);
  }

  window.accueil = { ouvrir, fermer };
})();
