# accounts/username_validation.py

import re
from better_profanity import profanity

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def is_valid_format(username: str) -> bool:
    if not username:
        return True

    return bool(_USERNAME_RE.match(username))


def contains_profanity(username: str) -> bool:
    return profanity.contains_profanity(username)


def is_valid_username(username: str) -> bool:
    if not is_valid_format(username):
        return False

    if contains_profanity(username):
        return False

    return True