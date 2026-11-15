// Flat map (2D) of a celestial body in equirectangular projection (Leaflet, CRS EPSG:4326).
// Latitude and longitude are straight axes here: this is the native format for Moon and Mars maps,
// and the poles remain visible (stretched across the entire width, as on any flat map).
//
// Used by lune.html and mars.html.

window.CartePlane = class CartePlane {
  /**
   * @param {object} o
   * @param {HTMLElement} o.element   map container
   * @param {number} o.rayonKm        body radius (for displayed distances)
   * @param {string} o.image          equirectangular image of the whole body (data URL), always displayed underneath
   * @param {object} [o.tuiles]       { url, maxZoom }: finer tiles on top (2 x 1 grid at level 0)
   * @param {function} [o.surMouvement]  called after each movement
   * @param {function} [o.surSurvol]     called with {lat, lng} or null on hover
   */
  constructor(o) {
    this.o = o;
    this.element = o.element;
    this.monde = L.latLngBounds([[-90, -180], [90, 180]]);
    this.carte = L.map(o.element, {
      crs: L.CRS.EPSG4326,
      zoomControl: false,
      attributionControl: false,
      keyboard: false,
      worldCopyJump: false,
      maxBounds: this.monde.pad(0.05),
      maxBoundsViscosity: 1,
      minZoom: 0,
      maxZoom: 9,
      zoomSnap: 0.25,
      zoomDelta: 0.5,
      wheelPxPerZoomLevel: 90,
    });
    this.fond = L.imageOverlay(o.image, this.monde).addTo(this.carte);
    this.tuiles = null;
    if (o.tuiles) this.changerTuiles(o.tuiles);
    this.grille = L.layerGroup();

    this.carte.on("moveend zoomend", () => o.surMouvement && o.surMouvement());
    this.carte.on("mousemove", (e) => o.surSurvol && o.surSurvol(this.normaliser(e.latlng)));
    this.carte.on("mouseout", () => o.surSurvol && o.surSurvol(null));
    this.cadrerMonde(false);
  }

  normaliser({ lat, lng }) {
    return { lat: Math.max(-90, Math.min(90, lat)), lng: Math.max(-180, Math.min(180, lng)) };
  }

  /** Replaces fine tiles ({ url, maxZoom }); null to display only the background image. */
  changerTuiles(t) {
    if (this.tuiles) this.carte.removeLayer(this.tuiles);
    this.tuiles = null;
    if (!t) return;
    this.tuiles = L.tileLayer(t.url, {
      bounds: this.monde,
      noWrap: true,
      maxNativeZoom: t.maxZoom,
      maxZoom: 9,
      errorTileUrl: "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==",
    }).addTo(this.carte);
  }

  changerImage(url) { this.fond.setUrl(url); }

  /** Latitude and longitude lines; spacing follows the zoom level. */
  afficherGrille(visible) {
    this.grilleVisible = visible;
    if (this._majGrille) this.carte.off("zoomend", this._majGrille);
    this.grille.remove();
    if (!visible) return;
    this._majGrille = () => {
      this.grille.clearLayers();
      const z = this.carte.getZoom();
      const pas = z < 2 ? 30 : z < 4 ? 10 : z < 6 ? 5 : 1;
      // White line on a dark border: readable on light ground (Moon) as well as dark ground.
      const styles = [
        { color: "#000000", weight: 2.4, opacity: 0.28, interactive: false },
        { color: "#ffffff", weight: 0.9, opacity: 0.7, interactive: false },
      ];
      for (const style of styles) {
        for (let lat = -90 + pas; lat < 90; lat += pas) this.grille.addLayer(L.polyline([[lat, -180], [lat, 180]], style));
        for (let lng = -180; lng <= 180; lng += pas) this.grille.addLayer(L.polyline([[-90, lng], [90, lng]], style));
      }
    };
    this._majGrille();
    this.carte.on("zoomend", this._majGrille);
    this.grille.addTo(this.carte);
  }

  // ------------------------------------------------------------------ view

  /** Zoom level at which `largeurDeg` degrees of longitude fill the window width. */
  zoomPourLargeur(largeurDeg) {
    const w = this.element.clientWidth || window.innerWidth;
    return Math.log2((360 * w) / (512 * Math.max(0.01, largeurDeg)));
  }

  /** Executes `action` immediately, or at the end of an ongoing animated zoom (otherwise Leaflet would cancel it). */
  apresAnimation(action) {
    if (this.carte._animatingZoom) this.carte.once("zoomend", action);
    else action();
  }

  cadrerMonde(anime = true) {
    this.apresAnimation(() => {
      this.carte.invalidateSize();
      this.carte.fitBounds(this.monde, { animate: anime });
    });
  }

  allerA(lat, lng, largeurDeg, anime = true) {
    this.apresAnimation(() => {
      const z = Math.max(this.carte.getMinZoom(), Math.min(9, this.zoomPourLargeur(largeurDeg)));
      if (anime) this.carte.flyTo([lat, lng], z, { duration: 1.2 });
      else this.carte.setView([lat, lng], z, { animate: false });
    });
  }

  centre() { return this.normaliser(this.carte.getCenter()); }

  /** Visible terrain width (in degrees of longitude). */
  largeurDeg() {
    const b = this.carte.getBounds();
    return Math.min(360, b.getEast() - b.getWest());
  }

  /** Visible width in kilometers, measured at the center of the view. */
  largeurKm() {
    const lat = this.centre().lat * (Math.PI / 180);
    return this.largeurDeg() * (Math.PI / 180) * this.o.rayonKm * Math.max(0.05, Math.cos(lat));
  }

  zoomer(delta) { this.carte.setZoom(this.carte.getZoom() + delta); }
  deplacer(dx, dy) { this.carte.panBy([dx, dy]); }
  rafraichir() { this.carte.invalidateSize(); }
};

// ------------------------------------------------------------------ 3D: careful detection and creation

/** True if the browser can create a WebGL 2 context (required for three.js / globe.gl). */
window.webgl2Disponible = function () {
  try {
    const gl = document.createElement("canvas").getContext("webgl2");
    if (!gl) return false;
    const ext = gl.getExtension("WEBGL_lose_context");
    if (ext) ext.loseContext();
    return true;
  } catch (e) {
    return false;
  }
};

/**
 * Creates the globe.gl globe, or returns null if 3D is impossible (no WebGL 2, graphics driver
 * refused...). A second attempt uses lighter settings (no antialiasing, low power).
 */
window.creerGlobe3D = function (conteneur) {
  if (!window.Globe) return null;
  if (!window.webgl2Disponible()) {
    console.warn("WebGL 2 unavailable in this browser: the page switches to the 2D map.");
    return null;
  }
  const essais = [null, { antialias: false, powerPreference: "low-power", failIfMajorPerformanceCaveat: false }];
  for (const rendererConfig of essais) {
    try {
      return new Globe(conteneur, { animateIn: false, waitForGlobeReady: true, ...(rendererConfig ? { rendererConfig } : {}) });
    } catch (e) {
      console.warn("Could not create the 3D globe:", e.message);
      conteneur.innerHTML = "";
    }
  }
  return null;
};

/** globe.gl draws its grid (every 10°) in nearly transparent gray: we make it legible. */
window.renforcerGrille3D = function (globe) {
  if (!globe) return;
  globe.scene().traverse((o) => {
    if (o.isLineSegments && o.material && o.material.isLineBasicMaterial) {
      o.material.color.set("#ffffff");
      o.material.opacity = 0.5;
      o.material.needsUpdate = true;
      o.scale.setScalar(1.002); // just above the surface, otherwise the sphere half-hides it
      o.renderOrder = 1;
    }
  });
};