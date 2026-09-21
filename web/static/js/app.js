// WorldWalker front end — vanilla JS, no framework.
// Talks to app.py's /api/places/*, /api/journey/start. Owns no travel
// logic itself: pure UI state + fetch calls, matching the rest of this
// project's "UI reports to the backend, never decides for it" shape.

(() => {
  "use strict";

  const DEBOUNCE_MS = 220;
  const MIN_CHARS = 2;

  // ---------- Theme toggle ----------
  // The <head> inline script already set data-theme before first paint
  // (see index.html) - this just wires up the switch and persists changes.

  const themeToggle = document.getElementById("theme-toggle");

  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    themeToggle.setAttribute("aria-pressed", String(theme === "light"));
    themeToggle.setAttribute("aria-label", theme === "light" ? "Switch to dark mode" : "Switch to light mode");
    try {
      localStorage.setItem("ww-theme", theme);
    } catch (e) {
      // Private browsing / storage disabled — theme just won't persist.
    }
  }

  applyTheme(currentTheme());
  themeToggle.addEventListener("click", () => {
    applyTheme(currentTheme() === "light" ? "dark" : "light");
  });

  // ---------- Trip type toggle ----------

  const tripPills = document.querySelectorAll(".trip-pill");
  tripPills.forEach((pill) => {
    pill.addEventListener("click", () => {
      tripPills.forEach((p) => {
        p.classList.toggle("is-active", p === pill);
        p.setAttribute("aria-checked", String(p === pill));
      });
    });
  });

  function tripType() {
    const active = document.querySelector(".trip-pill.is-active");
    return active ? active.dataset.trip : "round";
  }

  // ---------- Autocomplete ----------

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function highlight(text, query) {
    const safe = escapeHtml(text);
    const q = query.trim();
    if (!q) return safe;
    const idx = safe.toLowerCase().indexOf(escapeHtml(q).toLowerCase());
    if (idx === -1) return safe;
    return safe.slice(0, idx) + "<mark>" + safe.slice(idx, idx + q.length) + "</mark>" + safe.slice(idx + q.length);
  }

  class PlaceField {
    constructor(fieldId, inputId, listId) {
      this.field = document.getElementById(fieldId);
      this.input = document.getElementById(inputId);
      this.list = document.getElementById(listId);
      this.clearBtn = this.field.querySelector(".field-clear");

      this.results = [];
      this.activeIndex = -1;
      this.debounceTimer = null;
      this.controller = null;
      this.confirmedValue = "";

      this.input.addEventListener("input", () => this.onInput());
      this.input.addEventListener("keydown", (e) => this.onKeydown(e));
      this.input.addEventListener("focus", () => {
        if (this.results.length && this.input.value.trim().length >= MIN_CHARS) this.open();
      });
      this.clearBtn.addEventListener("click", () => this.clear());

      document.addEventListener("click", (e) => {
        if (!this.field.contains(e.target)) this.close();
      });
    }

    get value() {
      return this.input.value.trim();
    }

    set value(v) {
      this.input.value = v;
      this.confirmedValue = v;
      this.clearBtn.hidden = !v;
    }

    onInput() {
      this.clearBtn.hidden = !this.input.value;
      const query = this.value;

      if (query.length < MIN_CHARS) {
        this.showEmpty(query.length ? "Keep typing…" : null);
        return;
      }

      clearTimeout(this.debounceTimer);
      this.debounceTimer = setTimeout(() => this.search(query), DEBOUNCE_MS);
    }

    async search(query) {
      if (this.controller) this.controller.abort();
      this.controller = new AbortController();

      try {
        const res = await fetch(`/api/places/search?q=${encodeURIComponent(query)}`, {
          signal: this.controller.signal,
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        // A slower, now-stale response for an earlier keystroke — drop it.
        if (this.value !== query) return;

        this.results = data.results || [];
        this.render(query);
      } catch (err) {
        if (err.name === "AbortError") return;
        this.results = [];
        // this.showEmpty("Search unavailable — try again in a moment.");
      }
    }

    render(query) {
      if (!this.results.length) {
        // this.showEmpty("No matches yet — try a different spelling.");
        return;
      }
      this.activeIndex = -1;
      this.list.innerHTML = this.results
        .map(
          (r, i) => `
        <li class="suggestion" role="option" data-index="${i}" id="${this.list.id}-opt-${i}">
          <svg class="icon" viewBox="0 0 24 24" fill="none"><path d="M12 22s7-7.58 7-13A7 7 0 0 0 5 9c0 5.42 7 13 7 13Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><circle cx="12" cy="9" r="2.5" stroke="currentColor" stroke-width="1.8"/></svg>
          <span class="suggestion-text">
            <span class="suggestion-primary">${highlight(r.primary, query)}</span>
            ${r.secondary ? `<span class="suggestion-secondary">${escapeHtml(r.secondary)}</span>` : ""}
          </span>
        </li>`
        )
        .join("");

      this.list.querySelectorAll(".suggestion").forEach((el) => {
        el.addEventListener("mousedown", (e) => {
          e.preventDefault();
          this.select(Number(el.dataset.index));
        });
      });

      this.open();
    }

    showEmpty(message) {
      this.results = [];
      this.activeIndex = -1;
      if (!message) {
        this.close();
        return;
      }
      this.list.innerHTML = `<li class="suggestion is-empty">${escapeHtml(message)}</li>`;
      this.open();
    }

    open() {
      this.list.hidden = false;
      this.input.setAttribute("aria-expanded", "true");
    }

    close() {
      this.list.hidden = true;
      this.input.setAttribute("aria-expanded", "false");
      this.activeIndex = -1;
    }

    select(index) {
      const choice = this.results[index];
      if (!choice) return;
      this.value = choice.value;
      this.close();
    }

    clear() {
      this.value = "";
      this.results = [];
      this.close();
      this.input.focus();
    }

    onKeydown(e) {
      const rows = this.list.querySelectorAll(".suggestion:not(.is-empty)");
      if (this.list.hidden || !rows.length) {
        if (e.key === "Escape") this.close();
        return;
      }

      if (e.key === "ArrowDown") {
        e.preventDefault();
        this.activeIndex = Math.min(this.activeIndex + 1, rows.length - 1);
        this.highlightActive(rows);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        this.activeIndex = Math.max(this.activeIndex - 1, 0);
        this.highlightActive(rows);
      } else if (e.key === "Enter") {
        if (this.activeIndex >= 0) {
          e.preventDefault();
          this.select(this.activeIndex);
        }
      } else if (e.key === "Escape") {
        this.close();
      }
    }

    highlightActive(rows) {
      rows.forEach((el, i) => el.classList.toggle("is-active", i === this.activeIndex));
      const active = rows[this.activeIndex];
      if (active) active.scrollIntoView({ block: "nearest" });
    }
  }

  const fromField = new PlaceField("field-from", "input-from", "list-from");
  const toField = new PlaceField("field-to", "input-to", "list-to");

  // ---------- Swap ----------

  const swapBtn = document.getElementById("swap-btn");
  swapBtn.addEventListener("click", () => {
    const a = fromField.value;
    const b = toField.value;
    fromField.value = b;
    toField.value = a;

    swapBtn.classList.add("is-spinning");
    setTimeout(() => swapBtn.classList.remove("is-spinning"), 260);
  });

  // ---------- Current location ----------

  const useLocationBtn = document.getElementById("use-current-location");
  useLocationBtn.addEventListener("click", () => {
    // Silent on failure by design: a denied/failed lookup is always
    // retryable (grant the permission, click again), so it doesn't earn
    // an error panel - just log it for anyone debugging.
    if (!navigator.geolocation) {
      console.warn("Geolocation unsupported in this browser.");
      return;
    }

    useLocationBtn.classList.add("is-loading");
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const { latitude, longitude } = pos.coords;
          const res = await fetch(`/api/places/reverse?lat=${latitude}&lng=${longitude}`);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data = await res.json();
          fromField.value = data.place;
        } catch (err) {
          console.warn("Reverse geocode failed:", err);
        } finally {
          useLocationBtn.classList.remove("is-loading");
        }
      },
      (err) => {
        useLocationBtn.classList.remove("is-loading");
        console.warn("Geolocation failed:", err.message || err);
      },
      { timeout: 8000 }
    );
  });

  // ---------- Start Walking ----------

  const startBtn = document.getElementById("start-btn");

  startBtn.addEventListener("click", async () => {
    const from = fromField.value;
    const to = toField.value;

    // Silent by design: an incomplete form isn't an error, it's just not
    // done yet — no box, nothing happens until both fields are filled.
    if (!from || !to) return;

    startBtn.disabled = true;

    // Jump to the map screen immediately instead of waiting here with a
    // swapped-out button label — web/static/js/trip.js's loading state
    // (a spinner over the map area) carries the "hang on" messaging from
    // here on, not this button.
    window.TripView.showLoading(from, to);

    try {
      const res = await fetch("/api/journey/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ from_place: from, to_place: to, round_trip: tripType() === "round" }),
      });
      const data = await res.json();

      if (!res.ok) {
        console.warn("Couldn't start that walk:", data.error || res.status);
        window.TripView.showError(data.error || "Couldn't start that walk — try again.");
      } else if (data.coming_soon) {
        // A real external dependency (geocoding/routing) hiccuped -
        // logged for debugging, but the user just sees a plain retry
        // message on the map screen they're already looking at, not a
        // bounce back to the search form.
        console.warn("Route planning failed for this attempt:", from, "->", to);
        window.TripView.showError("Couldn't plan that route — try again in a moment.");
      } else {
        // The map/metrics view (web/static/js/trip.js) takes over from
        // here — this card's job (plan the walk) is done.
        window.TripView.show(data);
        refreshTripsBadge();
      }
    } catch (err) {
      console.warn("Network error starting walk:", err);
      window.TripView.showError("Network error — try again.");
    } finally {
      startBtn.disabled = false;
    }
  });

  // ---------- Trips panel (list icon in the topbar, and again in the
  // top-left corner of the map screen) ----------
  // Both trigger buttons only exist in the DOM once a Google Health
  // connection is active (see web/templates/index.html's `is_connected`
  // checks) - trips are meaningless to show before then, so this whole
  // section is a no-op when neither button was rendered.

  const tripsBtn = document.getElementById("trips-btn");
  const tripViewTripsBtn = document.getElementById("trip-view-trips-btn");

  if (tripsBtn || tripViewTripsBtn) {
    const tripsBtnBadge = document.getElementById("trips-btn-badge");
    const tripsPanel = document.getElementById("trips-panel");
    const tripsPanelBackdrop = document.getElementById("trips-panel-backdrop");
    const tripsPanelClose = document.getElementById("trips-panel-close");
    const tripsLoading = document.getElementById("trips-loading");
    const tripsListActive = document.getElementById("trips-list-active");
    const tripsListPast = document.getElementById("trips-list-past");
    const tripsEmptyActive = document.getElementById("trips-empty-active");
    const tripsEmptyPast = document.getElementById("trips-empty-past");
    const tripsBulkBar = document.getElementById("trips-bulk-bar");
    const tripsBulkCount = document.getElementById("trips-bulk-count");
    const tripsBulkCancel = document.getElementById("trips-bulk-cancel");
    const tripsBulkDelete = document.getElementById("trips-bulk-delete");

    const ACTIVE_STATUSES = new Set(["active", "paused"]);
    const selectedTripIds = new Set();
    let allTrips = [];

    function metersToMilesStr(meters) {
      return `${(meters / 1609.344).toFixed(1)} mi`;
    }

    function thumbnailSvg(routePoints) {
      if (!routePoints || routePoints.length < 2) {
        return '<svg viewBox="0 0 52 52"></svg>';
      }
      const lats = routePoints.map((p) => p.lat);
      const lngs = routePoints.map((p) => p.lng);
      const minLat = Math.min(...lats), maxLat = Math.max(...lats);
      const minLng = Math.min(...lngs), maxLng = Math.max(...lngs);
      const spanLat = maxLat - minLat || 1;
      const spanLng = maxLng - minLng || 1;
      const pad = 6;
      const size = 52;
      const points = routePoints
        .map((p) => {
          const x = pad + ((p.lng - minLng) / spanLng) * (size - pad * 2);
          const y = pad + (1 - (p.lat - minLat) / spanLat) * (size - pad * 2);
          return `${x.toFixed(1)},${y.toFixed(1)}`;
        })
        .join(" ");
      return `<svg viewBox="0 0 ${size} ${size}">
        <polyline points="${points}" fill="none" stroke="var(--blue)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>`;
    }

    function tripCardHtml(trip) {
      const isActive = ACTIVE_STATUSES.has(trip.status);
      const isSelected = selectedTripIds.has(trip.trip_id);
      const statusLabel = trip.status.charAt(0).toUpperCase() + trip.status.slice(1);

      const actionButtons = isActive
        ? `
          <button type="button" class="trip-card-action is-pause-resume" data-action="${trip.status === "paused" ? "resume" : "pause"}" aria-label="${trip.status === "paused" ? "Resume trip" : "Pause trip"}">
            ${
              trip.status === "paused"
                ? '<svg class="icon icon-sm" viewBox="0 0 24 24" fill="none"><path d="M7 5v14l12-7-12-7Z" fill="currentColor"/></svg>'
                : '<svg class="icon icon-sm" viewBox="0 0 24 24" fill="none"><rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor"/><rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor"/></svg>'
            }
          </button>`
        : "";

      return `
        <li class="trip-card ${isSelected ? "is-selected" : ""}" data-trip-id="${trip.trip_id}">
          <input type="checkbox" class="trip-card-select" aria-label="Select trip" ${isSelected ? "checked" : ""} />
          <div class="trip-card-thumb">${thumbnailSvg(trip.thumbnail_route)}</div>
          <div class="trip-card-body">
            <div class="trip-card-route">
              <span>${escapeHtml(trip.from_place)}</span>
              <svg class="icon icon-sm" viewBox="0 0 24 24" fill="none"><path d="M5 12h14m0 0-5-5m5 5-5 5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
              <span>${escapeHtml(trip.to_place)}</span>
            </div>
            <div class="trip-card-stats">
              <span>${metersToMilesStr(trip.distance_walked_m)} / ${metersToMilesStr(trip.total_distance_m)}</span>
              <span class="trip-card-progress"><span class="trip-card-progress-fill" style="width:${Math.min(100, trip.percent_complete).toFixed(0)}%"></span></span>
            </div>
            <span class="trip-card-status is-${trip.status}">${statusLabel}</span>
          </div>
          <div class="trip-card-actions">
            ${actionButtons}
            <button type="button" class="trip-card-action is-delete" data-action="delete" aria-label="Delete trip">
              <svg class="icon icon-sm" viewBox="0 0 24 24" fill="none"><path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2m-9 0 1 12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
          </div>
        </li>`;
    }

    function renderTripsList() {
      const active = allTrips.filter((t) => ACTIVE_STATUSES.has(t.status));
      const past = allTrips.filter((t) => !ACTIVE_STATUSES.has(t.status));

      tripsListActive.innerHTML = active.map(tripCardHtml).join("");
      tripsListPast.innerHTML = past.map(tripCardHtml).join("");
      tripsEmptyActive.hidden = active.length > 0;
      tripsEmptyPast.hidden = past.length > 0;

      if (tripsBtnBadge) {
        tripsBtnBadge.hidden = active.length === 0;
        tripsBtnBadge.textContent = String(active.length);
      }

      updateBulkBar();
    }

    function updateBulkBar() {
      const count = selectedTripIds.size;
      tripsBulkBar.hidden = count === 0;
      tripsBulkCount.textContent = `${count} selected`;
    }

    async function loadTrips() {
      tripsLoading.hidden = false;
      try {
        const res = await fetch("/api/journey/list");
        if (!res.ok) return;
        const data = await res.json();
        allTrips = data.trips || [];
        renderTripsList();
      } catch (err) {
        console.warn("Couldn't load trips:", err);
      } finally {
        tripsLoading.hidden = true;
      }
    }

    async function refreshTripsBadge() {
      try {
        const res = await fetch("/api/journey/list");
        if (!res.ok) return;
        const data = await res.json();
        const activeCount = (data.trips || []).filter((t) => ACTIVE_STATUSES.has(t.status)).length;
        if (tripsBtnBadge) {
          tripsBtnBadge.hidden = activeCount === 0;
          tripsBtnBadge.textContent = String(activeCount);
        }
      } catch (err) {
        // Badge staying stale for a beat isn't worth surfacing.
      }
    }

    function openTripsPanel() {
      tripsPanel.hidden = false;
      tripsPanelBackdrop.hidden = false;
      tripsBtn?.setAttribute("aria-expanded", "true");
      tripViewTripsBtn?.setAttribute("aria-expanded", "true");
      loadTrips();
    }

    function closeTripsPanel() {
      tripsPanel.hidden = true;
      tripsPanelBackdrop.hidden = true;
      tripsBtn?.setAttribute("aria-expanded", "false");
      tripViewTripsBtn?.setAttribute("aria-expanded", "false");
      selectedTripIds.clear();
      updateBulkBar();
    }

    tripsBtn?.addEventListener("click", openTripsPanel);
    tripViewTripsBtn?.addEventListener("click", openTripsPanel);
    tripsPanelClose.addEventListener("click", closeTripsPanel);
    tripsPanelBackdrop.addEventListener("click", closeTripsPanel);

    tripsBulkCancel.addEventListener("click", () => {
      selectedTripIds.clear();
      renderTripsList();
    });

    tripsBulkDelete.addEventListener("click", async () => {
      if (!selectedTripIds.size) return;
      const tripIds = Array.from(selectedTripIds);
      try {
        await fetch("/api/journey/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ trip_ids: tripIds }),
        });
      } catch (err) {
        console.warn("Bulk delete failed:", err);
      }
      selectedTripIds.clear();
      await loadTrips();
    });

    async function handleTripCardClick(e) {
      const card = e.target.closest(".trip-card");
      if (!card) return;
      const tripId = card.dataset.tripId;

      const checkbox = e.target.closest(".trip-card-select");
      if (checkbox) {
        if (selectedTripIds.has(tripId)) selectedTripIds.delete(tripId);
        else selectedTripIds.add(tripId);
        renderTripsList();
        return;
      }

      const actionBtn = e.target.closest(".trip-card-action");
      if (actionBtn) {
        const action = actionBtn.dataset.action;
        if (action === "delete") {
          try {
            await fetch(`/api/journey/${tripId}`, { method: "DELETE" });
          } catch (err) {
            console.warn("Delete failed:", err);
          }
          await loadTrips();
        } else if (action === "pause" || action === "resume") {
          try {
            await fetch(`/api/journey/${tripId}/${action}`, { method: "POST" });
          } catch (err) {
            console.warn(`${action} failed:`, err);
          }
          await loadTrips();
        }
        return;
      }

      // Anywhere else on the card - if any trips are already selected, this
      // click extends the selection instead of jumping into the trip (matches
      // how most multi-select list UIs behave once a selection is active).
      if (selectedTripIds.size > 0) {
        if (selectedTripIds.has(tripId)) selectedTripIds.delete(tripId);
        else selectedTripIds.add(tripId);
        renderTripsList();
        return;
      }

      const trip = allTrips.find((t) => t.trip_id === tripId);
      if (!trip) return;
      closeTripsPanel();
      if (ACTIVE_STATUSES.has(trip.status)) {
        window.TripView.openTrip(tripId);
      }
    }

    tripsListActive.addEventListener("click", handleTripCardClick);
    tripsListPast.addEventListener("click", handleTripCardClick);

    // Populate the topbar badge on first load, without opening the panel.
    refreshTripsBadge();
  }
})();
