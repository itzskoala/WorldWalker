# accounts/email_validation.py
# Real email validation - syntax plus a real DNS MX lookup to confirm the
# domain can actually receive mail. No third-party "email validation API"
# exists as a Vercel Marketplace integration (checked the messaging and
# dev-tools categories - nothing fits that specific capability), so this
# does the same two checks such a service would, with no new paid vendor
# or API key required.
#
# Used two places: GET /auth/validate-email (accounts/router.py) is what
# frontend/src/pages/AuthPage.tsx calls in real time as someone types/
# blurs the signup form's email field, and accounts/service.py's
# start_email_signup() re-runs the exact same check server-side before a
# code is ever sent - the client-side pass is a UX nicety, never trusted
# on its own.

import re

import dns.resolver

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Real network calls are slow - 3s is enough for a live domain to answer,
# short enough that a typo'd domain (NXDOMAIN, near-instant) or a dead
# one doesn't stall the request the user is waiting on.
_MX_LOOKUP_TIMEOUT_SECONDS = 3.0


def is_valid_syntax(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


def has_mx_record(domain: str) -> bool:
    """True if `domain` publishes at least one MX record - i.e. some mail
    server is actually willing to accept mail for it. Any lookup failure
    (NXDOMAIN, timeout, no MX record at all) means False; this never
    raises - a validation check that can crash the request is worse than
    one that's occasionally too strict on a slow/unusual DNS setup."""
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=_MX_LOOKUP_TIMEOUT_SECONDS)
        return len(answers) > 0
    except Exception:
        return False


def is_valid_email(email: str) -> bool:
    if not is_valid_syntax(email):
        return False
    domain = email.rsplit("@", 1)[-1]
    return has_mx_record(domain)
