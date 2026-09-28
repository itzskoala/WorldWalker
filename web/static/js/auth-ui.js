// web/static/js/auth-ui.js
// Wires web/templates/index.html's login/signup gate (#auth-gate) and
// the topbar user menu to web/static/js/auth.js, and decides which of
// #auth-loading / #auth-gate / #app-shell is on screen. Runs last (see
// index.html's script order) so window.Auth and window.TripView already
// exist by the time this fires.

(() => {
  "use strict";

  const authLoading = document.getElementById("auth-loading");
  const authGate = document.getElementById("auth-gate");
  const appShell = document.getElementById("app-shell");

  const authForm = document.getElementById("auth-form");
  const authEmail = document.getElementById("auth-email");
  const authPassword = document.getElementById("auth-password");
  const authError = document.getElementById("auth-error");
  const authSubmit = document.getElementById("auth-submit");
  const authSubmitLabel = document.getElementById("auth-submit-label");
  const authTabs = document.querySelectorAll("[data-auth-tab]");

  const userMenu = document.getElementById("user-menu");
  const userEmail = document.getElementById("user-email");
  const logoutBtn = document.getElementById("logout-btn");

  function activeMode() {
    const active = document.querySelector("[data-auth-tab].is-active");
    return active ? active.dataset.authTab : "login";
  }

  authTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      authTabs.forEach((t) => {
        t.classList.toggle("is-active", t === tab);
        t.setAttribute("aria-checked", String(t === tab));
      });
      const signingUp = tab.dataset.authTab === "signup";
      authSubmitLabel.textContent = signingUp ? "Sign up" : "Log in";
      authPassword.autocomplete = signingUp ? "new-password" : "current-password";
      hideError();
    });
  });

  function showError(message) {
    authError.textContent = message;
    authError.hidden = false;
  }

  function hideError() {
    authError.hidden = true;
  }

  function showGate() {
    authLoading.hidden = true;
    appShell.classList.add("is-auth-pending");
    authGate.hidden = false;
    if (userMenu) userMenu.hidden = true;
    // Any in-progress trip view/polling belongs to the session that just
    // ended - drop back to the search screen underneath the gate so
    // logging in again doesn't resume stale UI state.
    window.TripView?.hide();
  }

  function showApp() {
    authLoading.hidden = true;
    authGate.hidden = true;
    appShell.classList.remove("is-auth-pending");

    const user = window.Auth.getUser();
    if (userMenu && user) {
      userMenu.hidden = false;
      userEmail.textContent = user.email;
    }

    // The globe (web/static/js/globe.js) sized its canvas against
    // #app-shell while it was visibility:hidden - some canvas-backed
    // libraries only pick up a size change on an explicit resize, so
    // nudge one now that the real layout is visible.
    window.dispatchEvent(new Event("resize"));

    // Lets other scripts (web/static/js/app.js's trips badge) defer any
    // "load my data" fetch until there's actually a session to fetch it
    // with, instead of racing Auth.init() at script load.
    document.dispatchEvent(new CustomEvent("ww:authenticated"));
  }

  authForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    hideError();

    const email = authEmail.value.trim();
    const password = authPassword.value;
    if (!email || !password) return;

    authSubmit.disabled = true;
    try {
      if (activeMode() === "signup") {
        await window.Auth.signup(email, password);
      } else {
        await window.Auth.login(email, password);
      }
      await window.Auth.fetchMe();
      authForm.reset();
      showApp();
    } catch (err) {
      showError(err.message || "Something went wrong — try again.");
    } finally {
      authSubmit.disabled = false;
    }
  });

  logoutBtn?.addEventListener("click", async () => {
    await window.Auth.logout();
    showGate();
  });

  // web/static/js/auth.js's apiFetch fires this when a request comes
  // back 401 even after a refresh attempt - a session that died mid-use
  // (refresh cookie expired past its 7-day window, or logged out from
  // another tab), not just the very first page load.
  document.addEventListener("ww:unauthorized", showGate);

  window.Auth.init().then((authenticated) => {
    if (authenticated) showApp();
    else showGate();
  });
})();
