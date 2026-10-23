#description_generator.py
# Turns a checkpoint's name/coordinates into a short, tourist-flavor blurb.
# Talks to Ollama Cloud.

import os

import requests

SYSTEM_PROMPT = """You write short blurbs for WorldWalker, an app where users
take virtual walks along real-world routes and pass checkpoints - real
cities along the way.

Given a place name and coordinates, write one short, fun, tourist-facing
phrase of 10 words or fewer.

Rules:
- Output only the phrase itself. No preamble, quotation marks, markdown,
  or emoji.
- Sound like a fun local aside, not an encyclopedia entry or an ad.
- Never invent facts. If nothing specific is interesting, keep it simple
  and pleasant.
"""

BASE_URL = "https://ollama.com/api/generate"
MODEL = "gpt-oss:20b"


def generate_checkpoint_description(name, latitude, longitude):
    # OLLAMA_API_KEY, not OPENAI_API_KEY - see .env.example.
    api_key = os.environ.get("OLLAMA_API_KEY")

    response = requests.post(
        BASE_URL,
        json={"model": MODEL, "system": SYSTEM_PROMPT, "prompt": f"Place: {name}\nCoordinates: {latitude}, {longitude}", "stream": False},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["response"].strip()
