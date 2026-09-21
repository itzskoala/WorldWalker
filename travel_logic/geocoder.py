#geocoder.py
# Place name <-> coordinates. ABC so the provider (Nominatim now, Google
# Maps later) can be swapped without touching callers.

import json
import os
import random
import threading
import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

import requests
from dotenv import load_dotenv

from travel_logic.coordinates import Coordinates

load_dotenv()

_CACHE_MISS = object()


class Geocoder(ABC):
    @abstractmethod
    def geocode(self, place: str) -> Coordinates:
        """Place name -> coordinates. Raises ValueError if no match."""

    @abstractmethod
    def reverse_geocode(self, coords: Coordinates) -> str:
        """Coordinates -> a short place name (city/town/state)."""

    @abstractmethod
    def reverse_geocode_city(self, coords: Coordinates) -> Optional[str]:
        """City-tier name only (not town/village/hamlet/county) - None if
        this point isn't actually in a city. Used to filter route samples
        down to real, "important" places instead of every nearby dot."""

    @abstractmethod
    def search_places(self, query: str, limit: int = 5) -> List[str]:
        """Candidate place names for a live autocomplete dropdown, e.g.
        "ariz" -> ["Arizona, United States", ...]. Best-effort: returns []
        on a too-short query or a provider error rather than raising -
        callers are typing UIs, not journey-starting flows (that's still
        geocode(), which does raise)."""


class NominatimGeocoder(Geocoder):
    """Talks to the free, public Nominatim API - see
    https://operations.osmfoundation.org/policies/nominatim/ for the usage
    policy this class exists to respect: max ~1 request/second and a real
    contact in the User-Agent. Getting rate-limited (HTTP 429) during dev
    testing is what this class's throttle + cache are for - see
    dev_testing/TRIP_MAP.md.

    Every request this process makes to Nominatim, from any
    NominatimGeocoder instance (app.py and core/facade.py each construct
    their own), shares one throttle clock - they're all hitting the same
    host under the same policy, so the pacing has to be global, not
    per-instance."""

    BASE_URL = "https://nominatim.openstreetmap.org"
    DEFAULT_CACHE_PATH = Path("data/geocode_cache.json")

    _throttle_lock = threading.Lock()
    _last_request_at = 0.0

    def __init__(
        self,
        contact_email: Optional[str] = None,
        cache_path: Path | str = DEFAULT_CACHE_PATH,
        min_delay_s: float = 1.0,
        max_delay_s: float = 2.0,
    ):
        contact = contact_email or os.environ.get("GEOCODER_CONTACT_EMAIL", "")
        self._app_id = f"WorldWalker/1.0 ({contact})" if contact else "WorldWalker/1.0"
        self._min_delay_s = min_delay_s
        self._max_delay_s = max_delay_s
        self._cache_path = Path(cache_path)
        self._cache = self._load_cache()

    # ---------- local result cache (place name / rounded coords -> result) ----------
    # Keeps repeat dev testing (the same "Minneapolis" typed a dozen times)
    # from ever hitting Nominatim twice for the same lookup - see
    # _cache_key_for_coords()'s rounding for why nearby points share a hit
    # too.

    def _load_cache(self) -> dict:
        try:
            return json.loads(self._cache_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _save_cache(self) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(json.dumps(self._cache))
        except OSError:
            pass  # the in-memory cache still works for the rest of this process's life

    def _cache_get(self, key: str):
        return self._cache.get(key, _CACHE_MISS)

    def _cache_set(self, key: str, value) -> None:
        self._cache[key] = value
        self._save_cache()

    @staticmethod
    def _cache_key_for_coords(prefix: str, coords: Coordinates) -> str:
        # Rounded to ~11m (4 decimal places) - plenty of precision for
        # "which city is this near," and it means nearby route samples
        # (travel_logic/checkpoints.py walks the route in small steps)
        # collapse onto the same cache entry instead of each spending a
        # fresh request.
        return f"{prefix}:{round(coords.lat, 4)},{round(coords.lng, 4)}"

    # ---------- throttle + headers ----------

    def _headers(self) -> dict:
        # A random suffix per request, not just the stable app id below -
        # keeps every request individually identifiable while the app
        # name + contact email stay constant, which is what Nominatim's
        # policy actually asks for.
        return {"User-Agent": f"{self._app_id} req-{uuid.uuid4().hex[:8]}"}

    def _throttle(self) -> None:
        with NominatimGeocoder._throttle_lock:
            required_gap = random.uniform(self._min_delay_s, self._max_delay_s)
            elapsed = time.monotonic() - NominatimGeocoder._last_request_at
            if elapsed < required_gap:
                time.sleep(required_gap - elapsed)
            NominatimGeocoder._last_request_at = time.monotonic()

    def _get(self, path: str, params: dict, timeout: float) -> requests.Response:
        self._throttle()
        return requests.get(f"{self.BASE_URL}{path}", params=params, headers=self._headers(), timeout=timeout)

    # ---------- Geocoder interface ----------

    def geocode(self, place: str) -> Coordinates:
        key = f"geocode:{place.strip().lower()}"
        cached = self._cache_get(key)
        if cached is not _CACHE_MISS:
            if cached is None:
                raise ValueError(f"No match for '{place}'")
            return Coordinates(lat=cached["lat"], lng=cached["lng"])

        resp = self._get("/search", {"q": place, "format": "json", "limit": 1}, timeout=10)
        resp.raise_for_status()
        results = resp.json()
        if not results:
            self._cache_set(key, None)
            raise ValueError(f"No match for '{place}'")

        coords = Coordinates(lat=float(results[0]["lat"]), lng=float(results[0]["lon"]))
        self._cache_set(key, {"lat": coords.lat, "lng": coords.lng})
        return coords

    def reverse_geocode(self, coords: Coordinates) -> str:
        key = self._cache_key_for_coords("reverse", coords)
        cached = self._cache_get(key)
        if cached is not _CACHE_MISS:
            return cached

        resp = self._get("/reverse", {"lat": coords.lat, "lon": coords.lng, "format": "json"}, timeout=10)
        resp.raise_for_status()
        address = resp.json().get("address", {})
        place = (
            address.get("city")
            or address.get("town")
            or address.get("county")
            or address.get("state")
            or "Unknown"
        )
        self._cache_set(key, place)
        return place

    def reverse_geocode_city(self, coords: Coordinates) -> Optional[str]:
        key = self._cache_key_for_coords("reverse_city", coords)
        cached = self._cache_get(key)
        if cached is not _CACHE_MISS:
            return cached

        resp = self._get(
            "/reverse", {"lat": coords.lat, "lon": coords.lng, "format": "json", "addressdetails": 1}, timeout=10
        )
        resp.raise_for_status()
        city = resp.json().get("address", {}).get("city")
        self._cache_set(key, city)
        return city

    def search_places(self, query: str, limit: int = 5) -> List[str]:
        # None shows up for real: a UI Dropdown fires its "typing" event
        # with an empty/None value on focus, before any character is
        # typed - skip it the same as a too-short query, not an error.
        if not query or len(query.strip()) < 2:
            return []

        key = f"search:{query.strip().lower()}:{limit}"
        cached = self._cache_get(key)
        if cached is not _CACHE_MISS:
            return list(cached)

        try:
            resp = self._get("/search", {"q": query, "format": "json", "limit": limit}, timeout=5)
            resp.raise_for_status()
            results = [result["display_name"] for result in resp.json()]
            self._cache_set(key, results)
            return results
        except requests.RequestException:
            return []
