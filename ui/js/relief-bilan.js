// Terrain square for the summary's 3D slide (GET /api/relief), shared by bilan.js and analogues.js.
// The main page uses it to preload the relief as soon as the results arrive: the server keeps it in
// cache/relief/, and the summary has it immediately. Both pages must therefore request the exact same square.
(function () {
  const RAYON_KM = { earth: 6371.0088, mars: 3389.5, moon: 1737.4 };
  const rad = (d) => (d * Math.PI) / 180;
  /** Equidistant azimuthal projection around (lat0, lon0): (x eastward, y northward) in km. */
  function versPlan(lat, lon, lat0, lon0, R) {
    const p = rad(lat), l = rad(lon) - rad(lon0), p0 = rad(lat0);
    const cosc = Math.sin(p0) * Math.sin(p) + Math.cos(p0) * Math.cos(p) * Math.cos(l);
    const c = Math.acos(Math.max(-1, Math.min(1, cosc)));
    const k = c < 1e-9 ? 1 : c / Math.sin(c);
    return [R * k * Math.cos(p) * Math.sin(l), R * k * (Math.cos(p0) * Math.sin(p) - Math.sin(p0) * Math.cos(p) * Math.cos(l))];
  }
  /** Zone cells at resolution 6 (the saved zone may be compacted). */
  function cellules6(zone) {
    try { return window.h3.uncompactCells(zone, 6); } catch (e) { return zone; }
  }
  /** Center of the zone (average on the sphere) and side of the bounding square, in km (30 to 800, by 5 km). */
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
  /** Request path (without the server address). */
  const chemin = (corps, lat, lon, taille) =>
    `/api/relief?body=${corps}&lat=${lat.toFixed(4)}&lon=${lon.toFixed(4)}&size_km=${taille}&n=256`;
  window.reliefBilan = { RAYON_KM, cellules6, cadre, chemin };
})();