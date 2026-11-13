# Google OAuth verification checklist

Why WorldWalker shows "Google hasn't verified this app," what to configure
in Google Cloud Console, and what Google's verification process actually
requires. This is about the interactive consent screen at
`auth/google_health_auth.py`'s `build_auth_url()` (the `/auth/google/start`
→ Google consent → `/auth/google/callback` flow) - it has nothing to do
with `auth/register_webhook_subscription.py`, which authenticates as a
service account (`cloud-platform` scope) and never shows any consent
screen to a user.

## Why the warning appears

All 4 scopes WorldWalker requests are in Google's **Restricted** tier
(health data - confirmed in Google's own restricted-scopes list, same
tier as Gmail/Drive). For a Restricted-scope app, Google shows "hasn't
verified this app" to every user until the app completes:

1. **OAuth app verification** (branding review + scope justification +
   a demo video) - required regardless of user count.
2. **A CASA third-party security assessment** - required once the app
   passes 100 real connected users
   (developers.google.com/health/setup: "Supporting more than 100 users
   with the Google Health API requires completion of a third party
   security review").

Until verification is granted, the app is stuck in **Testing** status,
which caps it at 100 test users (each added by email to an explicit
allowlist in Cloud Console) and - this is the sharp edge - **refresh
tokens expire after 7 days** in Testing status. `auth/connections.py`'s
`get_valid_access_token()` already handles a rejected refresh correctly
(auto-disconnects the user), so nothing breaks, but every connected
user's Google Health connection will silently die and need reconnecting
roughly weekly until verification completes.

## What to configure in Google Cloud Console (manual, no code)

On the OAuth client already in `credentials.json`/`GOOGLE_OAUTH_CLIENT_ID`
(project `coral-core-506316-d1`, number `580356155767`):

1. **APIs & Services > OAuth consent screen**
   - User Type: **External** (already correct - Internal is Workspace-org-only, not applicable to a consumer app).
   - App name, support email, developer contact email.
   - App logo (required for verification, not just cosmetic).
   - **Application home page**: `https://world-walker-livid.vercel.app` (current Vercel production URL - swap for a custom domain if one gets added later; `*.vercel.app` is an accepted authorized domain).
   - **Application privacy policy link** and **Application terms of service link** - both required for verification and currently don't exist anywhere in this repo. These need real pages before verification can even be submitted (WorldWalker's frontend already has placeholder "Terms of Service"/"Privacy Policy" text in `frontend/src/pages/AuthPage.tsx` with no actual pages behind it).
   - Authorized domains: `vercel.app` (or the custom domain, once added).
2. **APIs & Services > Credentials > this OAuth 2.0 Client ID**
   - Authorized redirect URIs must include the real production callback: `https://world-walker-livid.vercel.app/auth/google/callback` (in addition to whatever local-dev URI is already there). This is what `GOOGLE_OAUTH_REDIRECT_URI` should be set to in the production environment's env vars.
3. **Publishing status**: stays "Testing" until verification is submitted and approved - don't click "Publish" expecting that alone to remove the warning; for Restricted scopes it won't.

## Scopes requested - verification-readiness

| Scope | Used for | Verification-ready? |
|---|---|---|
| `googlehealth.activity_and_fitness.readonly` | Steps/exercise → trip progress (`core/facade.py`'s `record_steps`/`record_workout`) - the app's core feature | Yes - real, demoable functionality |
| `googlehealth.profile.readonly` | `users.me.identity` → `healthUserId`, the only way a webhook notification maps back to a WorldWalker user (`auth/connections.py`) | Yes - foundational, demoable |

`sleep`/`health_metrics_and_measurements` (heart rate) are **not
requested** - WorldWalker pulled and logged that data to the console
(`services/google_health/webhook.py`) but never persisted or surfaced it
anywhere, so there was no real feature to demo for Google's reviewers.
Removed from `auth/google_health_auth.py`'s `SCOPES`,
`auth/register_webhook_subscription.py`'s subscriber config, and
`services/google_health/webhook.py`'s dispatch. The parsing code for both
(`services/fitbitMetrics/fitbit_sleep.py`, `fitbit_heart_rate.py`,
`services/google_health/client.py`'s `get_heart_rate_summary()`) is left
in place, tested, and ready - re-request both scopes (and re-wire
`register_webhook_subscription.py`'s MANUAL sleep-subscription handling,
see its git history) once a real feature uses that data.

## Verification submission checklist (once Console config above is done)

1. Cloud Console > OAuth consent screen > "Prepare for verification."
2. For each of the 2 scopes requested, provide:
   - Why the app needs it (one sentence - see table above).
   - A screen recording showing the exact in-app flow that uses it.
3. Privacy policy page must specifically disclose Google Health data use (not just a generic policy) - Google checks for this.
4. Submit. Google's typical turnaround is days to a few weeks; they may ask follow-up questions over email.
5. Once approved, the warning goes away for all users immediately - no CASA needed yet.
6. **Before crossing 100 real connected users**: budget for CASA (a paid, annual third-party security assessment - see Security Assessment docs linked from the OAuth consent screen). This is a real cost/timeline item to plan for separately, not something to do now.
