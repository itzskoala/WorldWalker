# database/encryption.py

import os

from cryptography.exceptions import InvalidSignature
from cryptography.fernet import Fernet, InvalidToken
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
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return _fernet.encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return _fernet.decrypt(value.encode()).decode()
        except (InvalidToken, InvalidSignature):
            return None
