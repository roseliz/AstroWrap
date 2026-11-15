// Carré de terrain de la diapositive 3D du bilan (GET /api/relief), partagé par bilan.js et analogues.js.
// La page principale s'en sert pour précharger le relief dès que les résultats arrivent : le serveur le garde dans
// cache/relief/, et le bilan l'a aussitôt. Les deux pages doivent donc demander exactement le même carré.
(function () {
  const RAYON_KM = { earth: 6371.0088, mars: 3389.5, moon: 1737.4 };
  const rad = (d) => (d * Math.PI) / 180;
  /** Projection azimutale équidistante autour de (lat0, lon0) : (x vers l'est, y vers le nord) en km. */
  function versPlan(lat, lon, lat0, lon0, R) {
    const p = rad(lat), l = rad(lon) - rad(lon0), p0 = rad(lat0);
    const cosc = Math.sin(p0) * Math.sin(p) + Math.cos(p0) * Math.cos(p) * Math.cos(l);
    const c = Math.acos(Math.max(-1, Math.min(1, cosc)));
    const k = c < 1e-9 ? 1 : c / Math.sin(c);
    return [R * k * Math.cos(p) * Math.sin(l), R * k * (Math.cos(p0) * Math.sin(p) - Math.sin(p0) * Math.cos(p) * Math.cos(l))];
  }
  /** Cellules de la zone à la résolution 6 (la zone enregistrée peut être compactée). */
  function cellules6(zone) {
    try { return window.h3.uncompactCells(zone, 6); } catch (e) { return zone; }
  }
  /** Centre de la zone (moyenne sur la sphère) et côté du carré qui la contient, en km (30 à 800, par 5 km). */
  function cadre(cellulesZone, corps) {
    const H = window.h3;
    let x = 0, y = 0, z = 0;
    cellulesZone.forEach((c) => {
      const [la, lo] = H.cellToLatLng(c);
      x += Math.cos(rad(la)) * Math.cos(rad(lo)); y += Math.cos(rad(la)) * Math.sin(rad(lo)); z += Math.sin(rad(la));
    });
    const lat = (Math.atan2(z, Math.hypot(x, y)) * 180) / Math.PI, lon = (Math.atan2(y, x) * 180) / Math.PI;
    let demi = 0;
    cellulesZone.forEach((c) => H.cellToBoundary(c).forEach(([la, lo]) => {
      const [u, v] = versPlan(la, lo, lat, lon, RAYON_KM[corps]);
      demi = Math.max(demi, Math.abs(u), Math.abs(v));
    }));
    return { lat, lon, taille: Math.min(800, Math.max(30, Math.ceil(demi * 2 * 1.3 / 5) * 5)) };
  }
  /** Chemin de la demande (sans l'adresse du serveur). */
  const chemin = (corps, lat, lon, taille) =>
    `/api/relief?body=${corps}&lat=${lat.toFixed(4)}&lon=${lon.toFixed(4)}&size_km=${taille}&n=256`;
  window.reliefBilan = { RAYON_KM, cellules6, cadre, chemin };
})();
