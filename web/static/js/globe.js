// WorldWalker header globe — a real NASA WebWorldWind globe (not an
// iframe), framed and auto-spun as a hero illustration, the way Google
// Flights uses a static drawing for its header banner.
//
// worldwind.min.js (loaded before this file, see index.html) exposes the
// WorldWind global. If that CDN is ever unreachable, WorldWind is simply
// undefined and this file no-ops - the header still renders as a plain
// dark band via CSS, nothing crashes.

(() => {
  "use strict";

  if (!window.WorldWind) {
    console.warn("WorldWind library unavailable — header stays a plain dark band.");
    return;
  }

  WorldWind.Logger.setLoggingLevel(WorldWind.Logger.LEVEL_WARNING);

  const wwd = new WorldWind.WorldWindow("globe-canvas");
  wwd.addLayer(new WorldWind.BMNGLayer());
  wwd.addLayer(new WorldWind.BMNGLandsatLayer());
  wwd.addLayer(new WorldWind.AtmosphereLayer());
  wwd.addLayer(new WorldWind.StarFieldLayer());

  // Pulled back and gently tilted, like a title-card illustration rather
  // than a navigable map. The canvas is pointer-events:none in CSS, so
  // this never needs to react to user dragging — it just spins.
  wwd.navigator.range = 2.4e7;
  wwd.navigator.tilt = 8;
  wwd.navigator.lookAtLocation.latitude = 18;
  wwd.navigator.lookAtLocation.longitude = -40;

  function spin() {
    wwd.navigator.lookAtLocation.longitude -= 0.03;
    if (wwd.navigator.lookAtLocation.longitude < -180) {
      wwd.navigator.lookAtLocation.longitude += 360;
    }
    wwd.redraw();
    requestAnimationFrame(spin);
  }
  requestAnimationFrame(spin);

  window.addEventListener("resize", () => wwd.redraw());
})();
