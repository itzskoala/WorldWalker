// web/static/js/home.js
// Owns the homescreen's activity card (web/templates/index.html's
// #activity-card) - the "what have I done" summary that sits between the
// globe hero and the plan-a-walk search card (web/static/js/app.js's
// #search-card). Talks to app.py's /api/journey/list and (for the one
// current trip, if any) /api/journey/state - no new endpoints.
//
// Renders one of three states:
//   - no trips ever started: a single empty-state line
//   - an active/paused trip exists: its route, progress bar, today's
//     steps, and a "Continue Walking" button straight into the map
//   - only finished trips: a lifetime one-liner (walks completed, total
//     distance) instead of a live progress bar
//
// Re-renders on "ww:authenticated" (first load) and "ww:home-shown"
// (whenever web/static/js/trip.js's hide() returns the user here, since
// a trip may have started/paused/finished while that view was up).

(() => {
  "use strict";

  const card = document.getElementById("activity-card");
  const searchCard = document.getElementById("search-card");
  if (!card) return;

  const METERS_PER_MILE = 1609.344;
  const CURRENT_STATUSES = new Set(["active", "paused"]);

  function miles(meters) {
    return (meters / METERS_PER_MILE).toFixed(1);
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function emptyStateHtml() {
    return `
      <p class="activity-empty">
        <span class="activity-empty-icon" aria-hidden="true">🥾</span>
        No walks yet — plan your first one below.
      </p>`;
  }

  function lifetimeStatsHtml(trips) {
    const completed = trips.filter((t) => t.status === "completed");
    if (!completed.length) return emptyStateHtml();

    const totalMeters = completed.reduce((sum, t) => sum + t.distance_walked_m, 0);
    return `
      <p class="activity-lifetime">
        <span class="activity-lifetime-icon" aria-hidden="true">🏆</span>
        <strong>${completed.length}</strong> walk${completed.length === 1 ? "" : "s"} completed
        <span class="activity-dot" aria-hidden="true">·</span>
        <strong>${miles(totalMeters)} mi</strong> total
      </p>`;
  }

  function currentTripHtml(state) {
    const pct = Math.min(100, state.percent_complete).toFixed(0);
    return `
      <div class="activity-current">
        <div class="activity-current-top">
          <div class="activity-current-route">
            <span>${escapeHtml(state.from_place)}</span>
            <svg class="icon icon-sm" viewBox="0 0 24 24" fill="none"><path d="M5 12h14m0 0-5-5m5 5-5 5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <span>${escapeHtml(state.to_place)}</span>
          </div>
          <span class="activity-current-pct">${pct}%</span>
        </div>

        <span class="trip-card-progress"><span class="trip-card-progress-fill" style="width:${pct}%"></span></span>

        <div class="activity-current-stats">
          <div class="metric">
            <span class="metric-value">${state.today_steps.toLocaleString()}</span>
            <span class="metric-label">Steps today</span>
          </div>
          <div class="metric">
            <span class="metric-value">${miles(state.distance_walked_m)} mi</span>
            <span class="metric-label">Walked</span>
          </div>
        </div>

        <button type="button" class="btn btn-continue" id="activity-continue-btn" data-trip-id="${state.trip_id}">
          Continue Walking
        </button>
      </div>`;
  }

  function setSecondary(isSecondary) {
    searchCard?.classList.toggle("is-secondary", isSecondary);
  }

  async function render() {
    try {
      const listRes = await window.Auth.apiFetch("/api/journey/list");
      if (!listRes.ok) return;
      const trips = (await listRes.json()).trips || [];

      const current = trips.find((t) => CURRENT_STATUSES.has(t.status));

      if (!current) {
        card.innerHTML = lifetimeStatsHtml(trips);
        card.hidden = false;
        setSecondary(false);
        return;
      }

      // The list endpoint's per-trip summary has no today_steps (see
      // core/facade.py's _trip_summary vs _build_map_state) - fetch the
      // one current trip's full state for that.
      const stateRes = await window.Auth.apiFetch(`/api/journey/state?trip_id=${current.trip_id}`);
      if (!stateRes.ok) return;
      const state = await stateRes.json();

      card.innerHTML = currentTripHtml(state);
      card.hidden = false;
      setSecondary(true);

      document.getElementById("activity-continue-btn")?.addEventListener("click", (e) => {
        window.TripView.openTrip(e.currentTarget.dataset.tripId);
      });
    } catch (err) {
      console.warn("Couldn't load your activity summary:", err);
    }
  }

  document.addEventListener("ww:authenticated", render);
  document.addEventListener("ww:home-shown", render);
})();
