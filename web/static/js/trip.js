// web/static/js/trip.js
// Owns the live trip map (MapLibre GL JS + OpenFreeMap tiles) and the
// metrics strip underneath it. Talks to app.py's /api/journey/* routes:
// POST /api/journey/start (app.js calls this and hands us the response),
// GET /api/journey/state?trip_id=... (polled here on a timer, and used to
// open a trip picked from app.js's trips panel), and the pause/resume
// routes this module's own header buttons call. Never touches app.js's
// search/autocomplete or trips-panel state directly, and vice versa - see
// web/static/css/style.css's ".trip-view" rules for the layout this
// drives.
//
// A user can have several trips going at once now, so this module always
// tracks which one is currently on screen (currentTripId) and rebuilds the
// map whenever that changes - see show()'s "different trip than what's
// already drawn" branch.
//
// The map has two layers of state, matching how the data actually works:
// the trip's full route and full checkpoint set exist on the server from
// the moment the trip starts, but only part of that is normally drawn.
//   - Always drawn: the full route as a thin muted line (so the user can
//     see where the path goes), the fixed start/end pins, and the green
//     "walked so far" line + "you are here" marker, which both grow on
//     every poll.
//   - Checkpoints stay literally absent from the map until the server
//     reports them hit - that's the whole "checkpoints don't appear until
//     you reach them" rule. Adding "?debug=1" to the page URL additionally
//     draws every not-yet-hit checkpoint as a faint ghost pin, so the
//     normally-invisible full checkpoint set can be checked against the
//     live trail while testing - see dev_testing/TRIP_MAP.md.

window.TripView = (function () {
  "use strict";

  const MAP_STYLE = "https://tiles.openfreemap.org/styles/liberty";
  const POLL_INTERVAL_MS = 20000;
  const METERS_PER_MILE = 1609.344;
  const DEBUG = new URLSearchParams(window.location.search).has("debug");

  const globeHeader = document.querySelector(".globe-header");
  const searchContent = document.querySelector("main.content");
  const tripView = document.getElementById("trip-view");
  const mapLoading = document.getElementById("trip-map-loading");
  const mapLoadingSpinner = document.getElementById("trip-map-loading-spinner");
  const mapLoadingErrorIcon = document.getElementById("trip-map-loading-error-icon");
  const mapLoadingText = document.getElementById("trip-map-loading-text");

  const backBtn = document.getElementById("trip-back-btn");
  const pauseBtn = document.getElementById("trip-pause-btn");
  const pauseIcon = pauseBtn.querySelector(".icon-pause");
  const resumeIcon = pauseBtn.querySelector(".icon-resume");
  const pauseLabel = pauseBtn.querySelector(".trip-pause-label");
  const titleFrom = document.getElementById("trip-view-from");
  const titleTo = document.getElementById("trip-view-to");
  const statusBadge = document.getElementById("trip-status-badge");

  const metricDistanceWalked = document.getElementById("metric-distance-walked");
  const metricDistanceLeft = document.getElementById("metric-distance-left");
  const metricCheckpoints = document.getElementById("metric-checkpoints");
  const metricStepsToday = document.getElementById("metric-steps-today");
  const metricStepsTotal = document.getElementById("metric-steps-total");
  const metricElapsed = document.getElementById("metric-elapsed");

  // Mutable module state - there is only ever one map on the page, so
  // these are plain variables rather than something passed around.
  let map = null;
  let youAreHereMarker = null;
  let pollTimerId = null;
  let currentTripId = null;
  let currentStatus = null;
  const checkpointMarkersByNumber = new Map();

  function toLngLat(coords) {
    return [coords.lng, coords.lat];
  }

  function metersToMiles(meters) {
    return meters / METERS_PER_MILE;
  }

  function formatMiles(meters) {
    return `${metersToMiles(meters).toFixed(1)} mi`;
  }

  function formatElapsed(totalSeconds) {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
  }

  function createMarkerElement(className) {
    const element = document.createElement("div");
    element.className = className;
    return element;
  }

  // ---------- Map setup (called whenever a different trip comes on screen) ----------

  function boundsForRoute(routeGeometry) {
    const bounds = new maplibregl.LngLatBounds();
    routeGeometry.forEach((point) => bounds.extend(toLngLat(point)));
    return bounds;
  }

  function destroyMap() {
    if (map) {
      map.remove();
      map = null;
    }
    youAreHereMarker = null;
    checkpointMarkersByNumber.clear();
  }

  function buildMap(state) {
    map = new maplibregl.Map({
      container: "trip-map",
      style: MAP_STYLE,
      bounds: boundsForRoute(state.route_geometry),
      fitBoundsOptions: { padding: 48 },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    map.on("load", () => {
      map.addSource("trip-route", { type: "geojson", data: routeLineGeoJson(state.route_geometry) });
      map.addLayer({
        id: "trip-route-line",
        type: "line",
        source: "trip-route",
        paint: { "line-color": "#9aa0a6", "line-width": 3, "line-dasharray": [2, 2] },
      });

      map.addSource("trip-walked", { type: "geojson", data: routeLineGeoJson(state.walked_geometry) });
      map.addLayer({
        id: "trip-walked-line",
        type: "line",
        source: "trip-walked",
        paint: { "line-color": "#1e8e3e", "line-width": 5 },
      });

      new maplibregl.Marker({ element: createMarkerElement("trip-marker-pin trip-marker-start") })
        .setLngLat(toLngLat(state.start))
        .addTo(map);
      new maplibregl.Marker({ element: createMarkerElement("trip-marker-pin trip-marker-end") })
        .setLngLat(toLngLat(state.end))
        .addTo(map);

      youAreHereMarker = new maplibregl.Marker({ element: createMarkerElement("trip-marker-you") })
        .setLngLat(toLngLat(state.current_position))
        .addTo(map);

      applyCheckpoints(state.checkpoints);
      mapLoading.hidden = true;
    });
  }

  function routeLineGeoJson(points) {
    return {
      type: "Feature",
      geometry: { type: "LineString", coordinates: points.map(toLngLat) },
    };
  }

  // ---------- Applying a fresh state (every poll, plus the first render) ----------

  function applyState(state) {
    if (map && map.getSource("trip-walked")) {
      map.getSource("trip-walked").setData(routeLineGeoJson(state.walked_geometry));
    }
    if (youAreHereMarker) {
      youAreHereMarker.setLngLat(toLngLat(state.current_position));
    }
    applyCheckpoints(state.checkpoints);
    applyMetrics(state);
    applyHeader(state);

    if (state.percent_complete >= 100) {
      stopPollingAndReturnToSearchSoon();
    }
  }

  function applyCheckpoints(checkpoints) {
    if (!map) return;
    checkpoints.forEach((checkpoint) => {
      const existing = checkpointMarkersByNumber.get(checkpoint.checkpoint_number);

      if (checkpoint.hit) {
        if (!existing || existing.isGhost) {
          if (existing) existing.marker.remove();
          const marker = new maplibregl.Marker({ element: createMarkerElement("trip-marker-checkpoint") })
            .setLngLat(toLngLat(checkpoint.coords))
            .addTo(map);
          checkpointMarkersByNumber.set(checkpoint.checkpoint_number, { marker, isGhost: false });
        }
        return;
      }

      // Not hit yet - stays invisible unless ?debug=1 is asking to see
      // the full, normally-hidden checkpoint set.
      if (DEBUG && !existing) {
        const marker = new maplibregl.Marker({ element: createMarkerElement("trip-marker-checkpoint is-ghost") })
          .setLngLat(toLngLat(checkpoint.coords))
          .addTo(map);
        checkpointMarkersByNumber.set(checkpoint.checkpoint_number, { marker, isGhost: true });
      }
    });
  }

  function applyMetrics(state) {
    metricDistanceWalked.textContent = formatMiles(state.distance_walked_m);
    metricDistanceLeft.textContent = formatMiles(state.distance_remaining_m);

    const hitCount = state.checkpoints.filter((checkpoint) => checkpoint.hit).length;
    metricCheckpoints.textContent = `${hitCount} / ${state.checkpoints.length}`;

    metricStepsToday.textContent = state.today_steps.toLocaleString();
    metricStepsTotal.textContent = state.total_steps.toLocaleString();
    metricElapsed.textContent = formatElapsed(state.elapsed_seconds);
  }

  function applyHeader(state) {
    currentStatus = state.status;
    titleFrom.textContent = state.from_place;
    titleTo.textContent = state.to_place;

    const isPaused = state.status === "paused";
    statusBadge.hidden = !isPaused;
    pauseBtn.classList.toggle("is-paused", isPaused);
    // .hidden (the IDL property) doesn't reliably reflect to the `hidden`
    // content attribute on <svg> elements in every engine - toggleAttribute
    // works directly on the attribute [hidden]'s CSS rule actually matches,
    // instead of silently no-op'ing like pauseIcon.hidden = ... did here.
    pauseIcon.toggleAttribute("hidden", isPaused);
    resumeIcon.toggleAttribute("hidden", !isPaused);
    pauseLabel.textContent = isPaused ? "Resume" : "Pause";
  }

  // ---------- Polling ----------

  function startPolling() {
    stopPolling();
    pollTimerId = window.setInterval(poll, POLL_INTERVAL_MS);
  }

  function stopPolling() {
    if (pollTimerId !== null) {
      window.clearInterval(pollTimerId);
      pollTimerId = null;
    }
  }

  async function poll() {
    if (!currentTripId) return;
    try {
      const res = await fetch(`/api/journey/state?trip_id=${currentTripId}`);
      if (res.status === 404) {
        // The trip finished, was deleted, or belongs to someone else now.
        hide();
        return;
      }
      if (!res.ok) return; // transient error - try again on the next tick
      applyState(await res.json());
    } catch (err) {
      console.warn("Trip state poll failed:", err); // keep polling - likely just a network blip
    }
  }

  function stopPollingAndReturnToSearchSoon() {
    stopPolling();
    window.setTimeout(hide, 2000); // a beat to let the user see the 100% state
  }

  // ---------- Show / hide the whole trip view ----------

  function enterTripView() {
    if (globeHeader) globeHeader.hidden = true;
    if (searchContent) searchContent.hidden = true;
    tripView.hidden = false;
  }

  // Called the instant "Start Walking" is clicked, before the new trip
  // even exists server-side - swaps straight to the map screen with a
  // loading overlay instead of leaving the user staring at the search
  // button. show() below replaces this with the real map once
  // /api/journey/start resolves.
  function showLoading(fromPlace, toPlace) {
    enterTripView();
    destroyMap();
    currentTripId = null;
    stopPolling();

    titleFrom.textContent = fromPlace;
    titleTo.textContent = toPlace;
    statusBadge.hidden = true;

    mapLoading.hidden = false;
    mapLoading.classList.remove("is-error");
    mapLoadingSpinner.hidden = false;
    // toggleAttribute, not .hidden = true - see applyHeader()'s comment on
    // why plain .hidden doesn't reliably work on <svg> elements here.
    mapLoadingErrorIcon.toggleAttribute("hidden", true);
    mapLoadingText.textContent = "Loading your walk…";
  }

  // Starting the trip failed server-side (a geocoding/routing hiccup, a
  // network error, ...) - stays on this screen rather than bouncing back
  // to search, since the user already committed to "Start Walking" and
  // the back button right above this is always there if they want out.
  function showError(message) {
    enterTripView();
    destroyMap();
    currentTripId = null;
    stopPolling();

    mapLoading.hidden = false;
    mapLoading.classList.add("is-error");
    mapLoadingSpinner.hidden = true;
    mapLoadingErrorIcon.toggleAttribute("hidden", false);
    mapLoadingText.textContent = message;
  }

  function show(state) {
    enterTripView();
    mapLoading.hidden = true;

    if (state.trip_id !== currentTripId) {
      destroyMap();
      currentTripId = state.trip_id;
      buildMap(state);
      // buildMap()'s work (tiles, sources, markers) waits on the map's own
      // "load" event, but the header/metrics strip has no such dependency -
      // show real numbers immediately instead of leaving zeros up until the
      // first poll, ~POLL_INTERVAL_MS later.
      applyMetrics(state);
      applyHeader(state);
    } else {
      applyState(state);
    }
    startPolling();
  }

  // Fetches one specific trip's full map state and shows it - what
  // app.js's trips panel calls when a trip card is clicked.
  async function openTrip(tripId) {
    try {
      const res = await fetch(`/api/journey/state?trip_id=${tripId}`);
      if (!res.ok) return;
      show(await res.json());
    } catch (err) {
      console.warn("Couldn't open that trip:", err);
    }
  }

  function hide() {
    stopPolling();
    tripView.hidden = true;
    if (globeHeader) globeHeader.hidden = false;
    if (searchContent) searchContent.hidden = false;
  }

  backBtn.addEventListener("click", hide);

  pauseBtn.addEventListener("click", async () => {
    if (!currentTripId) return;
    const action = currentStatus === "paused" ? "resume" : "pause";
    pauseBtn.disabled = true;
    try {
      const res = await fetch(`/api/journey/${currentTripId}/${action}`, { method: "POST" });
      if (res.ok) applyState(await res.json());
    } catch (err) {
      console.warn(`Couldn't ${action} this trip:`, err);
    } finally {
      pauseBtn.disabled = false;
    }
  });

  return { showLoading, showError, show, openTrip, hide };
})();
