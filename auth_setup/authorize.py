#!/usr/bin/env python3
# auth_setup/authorize.py
# One-time (or re-run if refresh ever breaks, or if SCOPES changes): grants
# your account's consent and saves .tokens.json. Run from repo root:
#   venv/bin/python3 auth_setup/authorize.py

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so `auth_setup` is importable

from auth_setup.google_health_auth import build_auth_url, exchange_code

print("1. Open this URL and approve access:\n")
print(build_auth_url())
print("\n2. You'll land on a redirect URL like https://www.google.com/?code=...")
print("   Copy everything after 'code=' (and before any '&').\n")

code = input("Paste the code here: ").strip()
exchange_code(code)
print("\nSaved .tokens.json - you're authorized.")
