// web/static/js/auth.js
// Frontend client for accounts/router.py's /auth/* endpoints. Matches
// that router's design exactly (see its own header comment): the access
// token lives in memory only, never localStorage/sessionStorage - a
// plain module-level variable that's gone on refresh - while the
// refresh token is an HTTP-only cookie the browser attaches to
// same-origin requests by itself, invisible to this script.
//
// Every other script (web/static/js/app.js, web/static/js/trip.js) calls
// window.Auth.apiFetch() instead of the bare fetch() for anything under
// /api/* - that's what attaches "Authorization: Bearer <token>" and
// transparently refreshes+retries once on a 401 (an expired 15-minute
// access token, see accounts/security.py's ACCESS_TOKEN_EXPIRE_MINUTES)
// before giving up and signaling the page to show the login gate again.

window.Auth = (function () {
  "use strict";

  let accessToken = null;
  let currentUser = null;
  let refreshPromise = null;

  function isAuthenticated() {
    return accessToken !== null;
  }

  function getUser() {
    return currentUser;
  }

  function clearSession() {
    accessToken = null;
    currentUser = null;
  }

  async function parseError(res, fallback) {
    try {
      const data = await res.json();
      return data.detail || fallback;
    } catch (e) {
      return fallback;
    }
  }

  // Coalesces concurrent refreshes (e.g. two protected requests both
  // hitting a 401 back-to-back) into a single /auth/refresh call instead
  // of a duplicate race that could rotate the token twice.
  async function refresh() {
    if (!refreshPromise) {
      refreshPromise = fetch("/auth/refresh", { method: "POST", credentials: "include" })
        .then(async (res) => {
          if (!res.ok) {
            clearSession();
            return false;
          }
          const data = await res.json();
          accessToken = data.access_token;
          return true;
        })
        .catch(() => {
          clearSession();
          return false;
        })
        .finally(() => {
          refreshPromise = null;
        });
    }
    return refreshPromise;
  }

  async function signup(email, password) {
    const res = await fetch("/auth/signup", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) throw new Error(await parseError(res, "Couldn't sign up — try again."));
    const data = await res.json();
    accessToken = data.access_token;
    return data;
  }

  async function login(email, password) {
    const res = await fetch("/auth/login", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) throw new Error(await parseError(res, "Incorrect email or password."));
    const data = await res.json();
    accessToken = data.access_token;
    return data;
  }

  async function logout() {
    try {
      await fetch("/auth/logout", { method: "POST", credentials: "include" });
    } catch (err) {
      console.warn("Logout request failed (clearing the local session anyway):", err);
    }
    clearSession();
  }

  async function fetchMe() {
    const res = await apiFetch("/auth/me");
    if (!res.ok) throw new Error("Couldn't load your account.");
    currentUser = await res.json();
    return currentUser;
  }

  // The one wrapper every authenticated fetch in this app goes through.
  // On a 401 it tries exactly one silent refresh+retry - not an infinite
  // loop - before surfacing the failure, since a second 401 right after
  // a successful refresh means the token really is no good (deactivated
  // user, revoked session), not a fluke worth retrying again.
  async function apiFetch(path, options = {}) {
    const withAuth = (token) => {
      const headers = new Headers(options.headers || {});
      if (token) headers.set("Authorization", `Bearer ${token}`);
      return Object.assign({}, options, { headers, credentials: "include" });
    };

    let res = await fetch(path, withAuth(accessToken));

    if (res.status === 401 && accessToken !== null) {
      const refreshed = await refresh();
      if (refreshed) {
        res = await fetch(path, withAuth(accessToken));
      }
    }

    if (res.status === 401) {
      clearSession();
      document.dispatchEvent(new CustomEvent("ww:unauthorized"));
    }

    return res;
  }

  // Called once on page load (see web/static/js/auth-ui.js): tries to
  // restore a session from the refresh cookie left by an earlier
  // login/signup before falling back to the login gate, so reloading the
  // tab - or coming back the next day, within the 7-day refresh window
  // (accounts/security.py's REFRESH_TOKEN_EXPIRE_DAYS) - doesn't sign
  // anyone out.
  async function init() {
    const restored = await refresh();
    if (!restored) return false;

    try {
      await fetchMe();
      return true;
    } catch (err) {
      clearSession();
      return false;
    }
  }

  return { init, login, signup, logout, apiFetch, fetchMe, isAuthenticated, getUser };
})();
