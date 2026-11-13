#accounts/email_validation.py

'''
Verify/validate email addresses before allowing someone to register an account
'''
import re

import dns.resolver

import secrets


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_MX_LOOKUP_TIMEOUT_SECONDS = 3.0


def is_valid_syntax(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


def has_mx_record(domain: str) -> bool:
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

#TODO: implement vertification code + email sending
def generate_verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"

#TODO: implement email sending with verifaction code
# def send_email():

#     to=email,
#     subject="WorldWalker Email Verification",
#     body=f"Your verification code is: {code}"
# )


