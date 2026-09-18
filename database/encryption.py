# database/encryption.py
# Application-level encryption for token columns - the key never touches
# SQL (unlike pgcrypto's pgp_sym_encrypt, which needs the key passed as a
# literal inside the query itself, risking it landing in query logs).
#
# Fernet (symmetric, authenticated encryption - AES128-CBC + HMAC under
# the hood) from the `cryptography` package: well-reviewed, not
# hand-rolled crypto.

import os

from cryptography.fernet import Fernet
from dotenv import load_dotenv
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

load_dotenv()

_KEY = os.environ.get("TOKEN_ENCRYPTION_KEY")
if not _KEY:
    raise RuntimeError(
        "TOKEN_ENCRYPTION_KEY is not set. Generate one with "
        '`python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` '
        "and add it to .env."
    )
_fernet = Fernet(_KEY.encode())


class EncryptedString(TypeDecorator):
    """A string column that's encrypted before it's written and decrypted
    after it's read, transparently - callers (models, application code,
    tests) just read/write plain strings and never handle ciphertext
    directly. That matters: it means a token can't accidentally end up
    stored in plaintext because someone forgot to call an encrypt
    function before an INSERT - there's no plaintext code path to forget."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return _fernet.encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return _fernet.decrypt(value.encode()).decode()
