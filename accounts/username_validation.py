# accounts/username_validation.py
# Format check for account usernames - letters, numbers, and underscores
# only, mirroring accounts/email_validation.py's syntax check. Used by
# both GET /auth/validate-username (the profile form's real-time check,
# frontend/src/components/profile/ProfileUsernameField.tsx) and
# accounts/service.py's update_username(), which re-runs it server-side
# before anything is persisted - the client-side pass is a UX nicety,
# never trusted on its own.

import re

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def is_valid_format(username: str) -> bool:
    # An empty username is allowed - User.username is nullable, "no
    # username set" isn't an invalid *character*, which is all this
    # checks.
    if not username:
        return True
    return bool(_USERNAME_RE.match(username))
