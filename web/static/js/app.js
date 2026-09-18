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
      onFieldsChanged();
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
      onFieldsChanged();
    }

    clear() {
      this.value = "";
      this.results = [];
      this.close();
      this.input.focus();
      onFieldsChanged();
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
    onFieldsChanged();
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
          onFieldsChanged();
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
  const resultPanel = document.getElementById("result-panel");

  function onFieldsChanged() {
    // A result/error from a previous attempt is stale the moment the user
    // touches either field again — clear it rather than leaving it stuck
    // on screen (and, since suggestion dropdowns can overflow past the
    // card's bottom edge, stuck behind/through them looking broken).
    resultPanel.hidden = true;
  }

  function showResult(kind, title, bodyHtml) {
    resultPanel.hidden = false;
    resultPanel.className = `result-panel is-${kind}`;
    resultPanel.innerHTML = `<p class="result-title">${escapeHtml(title)}</p>${bodyHtml}`;
  }

  startBtn.addEventListener("click", async () => {
    const from = fromField.value;
    const to = toField.value;

    // Silent by design: an incomplete form isn't an error, it's just not
    // done yet — no box, nothing happens until both fields are filled.
    if (!from || !to) return;

    startBtn.disabled = true;
    const originalLabel = startBtn.innerHTML;
    startBtn.innerHTML = "Plotting your route…";

    try {
      const res = await fetch("/api/journey/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ from_place: from, to_place: to, round_trip: tripType() === "round" }),
      });
      const data = await res.json();

      if (!res.ok) {
        // Failures are logged, not shown — no error boxes in this UI.
        console.warn("Couldn't start that walk:", data.error || res.status);
      } else if (data.coming_soon) {
        showResult(
          "pending",
          "🚧 Route planning is coming online soon",
          `<p class="result-stats">The UI is ready — <b>${escapeHtml(from)} → ${escapeHtml(to)}</b> will start tracking real steps once the travel-logic backend is wired up.</p>`
        );
      } else {
        showResult(
          "success",
          `🚶 Walking from ${escapeHtml(from)} to ${escapeHtml(to)}`,
          `<p class="result-stats">
             <span><b>${data.miles_remaining.toFixed(1)}</b> miles to go</span>
             <span><b>${data.landmark_count}</b> landmarks on the way</span>
             <span>ETA: <b>${escapeHtml(data.estimated_days_remaining ?? "take your first steps to find out")}</b></span>
           </p>`
        );
      }
    } catch (err) {
      console.warn("Network error starting walk:", err);
    } finally {
      startBtn.disabled = false;
      startBtn.innerHTML = originalLabel;
    }
  });
})();
