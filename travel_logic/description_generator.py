#description_generator.py
# Turns a checkpoint's name/coordinates into a short, tourist-flavor blurb.
# ABC so the model/provider (Ollama Cloud now, something else later) can
# swap without touching checkpoints.py - same pattern as Geocoder/RouteService.

import os
from abc import ABC, abstractmethod
import requests


SYSTEM_PROMPT = """You write short blurbs for WorldWalker, an app where users
take virtual walks along real-world routes and pass "checkpoints" - real
cities along the way.

Your only job: given a place name and its coordinates, write one short,
fun, tourist-facing phrase about that place (10 words or fewer).

This exact phrase is reused in three places, so it must work as plain,
standalone text in all of them:
- A phone push notification (gets truncated if too long)
- A caption next to the checkpoint on the website
- A single line in a recap email

Rules:
- Output ONLY the phrase itself. No preamble, no "Here's a fact:", no
  sign-off, no quotation marks, no markdown, no emoji.
- One short phrase, not a full paragraph or multiple sentences.
- Sound like a fun local aside, not an encyclopedia entry and not an ad.
- If you don't have anything specific and interesting to say, keep it
  simple and pleasant rather than inventing facts."""


class DescriptionGenerator(ABC):
    @abstractmethod
    def generate(self, prompt: str):
        """Send a prompt to the model, return its raw text response.
        Raises on a provider/network failure - callers decide how to
        degrade (checkpoints.generate_description falls back to "")."""


class AIDescriptionGenerator(DescriptionGenerator):
    BASE_URL = "https://ollama.com/api/generate"
    DEFAULT_MODEL = "gpt-oss:20b"

    def __init__(self, api_key: str = None, model: str = DEFAULT_MODEL):
        # Resolved lazily in generate(), not here - core/facade.py builds
        # one of these at import time (the module-level `travel_facade`
        # singleton), so raising on a missing/bad key in __init__ would
        # crash the whole app at startup instead of just this one
        # checkpoint's description degrading to the fallback text (see
        # travel_logic/checkpoints.py's generate_description(), which
        # already wraps generate() in a try/except for exactly this).
        self._api_key = api_key
        self._model = model

    def generate(self, prompt: str) -> str:
        # OLLAMA_API_KEY, not OPENAI_API_KEY - this class calls Ollama
        # Cloud (BASE_URL above), which 401s on an OpenAI-issued key.
        # Create one at https://ollama.com/settings/keys - see .env.example.
        api_key = self._api_key or os.environ.get("OLLAMA_API_KEY")
        if not api_key:
            raise RuntimeError("OLLAMA_API_KEY is not set - see .env.example.")

        resp = requests.post(
            self.BASE_URL,
            json={
                "model": self._model,
                "system": SYSTEM_PROMPT,
                "prompt": prompt,
                "stream": False,
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["response"].strip()
