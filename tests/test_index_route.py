# tests/test_index_route.py
# /, /login, /signup, and GET /api/config - the frontend (frontend/,
# built to frontend/dist/) has no server-side templating any more, so
# these routes carry no per-request/per-user state at all: every page
# route serves the exact same static SPA shell, and react-router
# (frontend/src/App.tsx) decides what to render client-side. The one
# genuinely dynamic bit that used to be baked into server-rendered HTML -
# the Google Sign-In client ID - now lives at GET /api/config instead
# (frontend/src/components/GoogleSignInButton.tsx fetches it once).

from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


def test_index_renders_the_spa_shell_with_no_per_user_state(connected_user_id):
    # connected_user_id fixture: some OTHER, fully connected user exists in
    # the database. There is no way for this response to reflect that (or
    # any) user's status - it's a static file, not a render - which is the
    # point: no "is anyone connected" leak is even possible any more.
    response = client.get("/")

    assert response.status_code == 200
    assert '<div id="root">' in response.text


def test_index_route_has_no_database_dependency_at_all():
    # Stronger than mocking a call and checking it's unused: app.py
    # doesn't even import SessionLocal any more, so there is no session
    # object any page route could reach for even by accident.
    import app as app_module

    assert not hasattr(app_module, "SessionLocal")


# --- /signup and /login: separate routes (so each has its own URL,
# bookmarkable/shareable), but - like / - just the same static SPA shell.
# react-router picks which screen to show from the URL client-side.

def test_signup_page_renders():
    response = client.get("/signup")
    assert response.status_code == 200
    assert '<div id="root">' in response.text


def test_login_page_renders():
    response = client.get("/login")
    assert response.status_code == 200
    assert '<div id="root">' in response.text


def test_every_page_route_serves_the_identical_shell():
    # Same bytes everywhere - proof there's no per-route server templating
    # left to diverge. An arbitrary client-side route (react-router path)
    # gets it too, which is exactly what makes a hard refresh on a deep
    # link work instead of 404ing.
    bodies = {path: client.get(path).text for path in ("/", "/login", "/signup", "/some/client/route")}
    assert len(set(bodies.values())) == 1


def test_unmatched_api_path_still_404s_instead_of_getting_the_spa_shell():
    # The SPA catch-all must not swallow a genuinely missing API route -
    # see app.py's API_PREFIXES check.
    response = client.get("/api/this-route-does-not-exist")
    assert response.status_code == 404


# --- GET /api/config: the one piece of real (if non-secret) server state
# a page route used to carry directly - accounts/router.py's Google
# OAuth is unaffected either way.

def test_public_config_carries_the_configured_google_client_id(monkeypatch):
    monkeypatch.setenv("GOOGLE_SIGNIN_CLIENT_ID", "test-client-id-123")
    monkeypatch.delenv("APPLE_SIGNIN_CLIENT_ID", raising=False)

    response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json() == {"google_client_id": "test-client-id-123", "apple_client_id": ""}


def test_public_config_is_empty_when_unconfigured(monkeypatch):
    monkeypatch.delenv("GOOGLE_SIGNIN_CLIENT_ID", raising=False)
    monkeypatch.delenv("APPLE_SIGNIN_CLIENT_ID", raising=False)

    response = client.get("/api/config")

    assert response.json() == {"google_client_id": "", "apple_client_id": ""}
