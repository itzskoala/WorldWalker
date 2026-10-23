#geocoder.py
# Place name <-> coordinates, via the free Nominatim API.

import os
import random
import threading
import time
import uuid

import requests
from dotenv import load_dotenv

from travel_logic.dataclasses.coordinates import Coordinates
from travel_logic.dataclasses.place import Place

load_dotenv()


def _place_dict(entry):
    """One LocalPlaceIndex entry -> the plain dict search_places() returns."""
    return {"value": entry["label"], "primary": entry["primary"], "secondary": entry["secondary"], "lat": entry["lat"], "lng": entry["lng"]}


def _split_display_name(display_name):
    """"Fargo, Cass County, North Dakota" -> ("Fargo", "Cass County, North Dakota")."""
    parts = []
    for part in display_name.split(","):
        stripped = part.strip()
        if stripped:
            parts.append(stripped)
    primary = parts[0] if parts else display_name
    return primary, ", ".join(parts[1:])


def _short_label(address):
    """Nominatim's structured address -> a concise "City, State" (US) or
    "City, Region, Country" label. None if there's too little structured
    data to build one - callers fall back to the full display_name."""
    city = address.get("city") or address.get("town") or address.get("village") or address.get("municipality")
    region = address.get("state") or address.get("state_district") or address.get("region") or address.get("province")
    country = address.get("country")

    if (address.get("country_code") or "").lower() == "us":
        if city and region:
            return f"{city}, {region}"
        return city or region or None

    parts = []
    for part in (city, region, country):
        if part:
            parts.append(part)
    return ", ".join(parts) if parts else None


def _place_entry(display_name, lat, lng, place_type, provider_id=None, label=None):
    """One LocalPlaceIndex entry. `label` is the shortened, user-facing
    text (falls back to display_name unshortened) - primary/secondary
    are derived from it."""
    label = label or display_name
    primary, secondary = _split_display_name(label)
    return {
        "display_name": display_name,
        "label": label,
        "primary": primary,
        "secondary": secondary,
        "lat": lat,
        "lng": lng,
        "type": place_type,
        "provider_id": provider_id,
    }


class LocalPlaceIndex:
    """A process-local, in-memory prefix index of places this process has
    already seen via a real Nominatim search - lets a short prefix
    ("F"/"Fa"/"Fargo") answer instantly, with no network call. Grows
    purely from real usage, no hardcoded city list."""

    def __init__(self, seed):
        self._entries = {}
        self.add(seed)

    def add(self, entries):
        for entry in entries:
            key = f"{round(entry['lat'], 4)},{round(entry['lng'], 4)}"
            self._entries[key] = entry

    def search(self, query, limit):
        q = query.strip().lower()
        if not q:
            return []

        matches = []
        for entry in self._entries.values():
            if entry["primary"].lower().startswith(q):
                matches.append(entry)
        matches.sort(key=lambda entry: (len(entry["primary"]), entry["primary"]))

        seen_labels = set()
        deduped = []
        for entry in matches:
            if entry["label"] in seen_labels:
                continue
            seen_labels.add(entry["label"])
            deduped.append(entry)
        return deduped[:limit]


class NominatimGeocoder:
    """Talks to the free, public Nominatim API - max ~1 request/second,
    a real contact in the User-Agent. The throttle clock and
    LocalPlaceIndex below are shared process-wide (class attributes),
    not per-instance - every NominatimGeocoder hits the same host under
    the same policy."""

    BASE_URL = "https://nominatim.openstreetmap.org"

    _throttle_lock = threading.Lock()
    _last_request_at = 0.0
    _local_index = LocalPlaceIndex([])

    def __init__(self, contact_email=None, min_delay_s=1.0, max_delay_s=2.0):
        contact = contact_email or os.environ.get("GEOCODER_CONTACT_EMAIL", "")
        self._app_id = f"WorldWalker/1.0 ({contact})" if contact else "WorldWalker/1.0"
        self._min_delay_s = min_delay_s
        self._max_delay_s = max_delay_s

    # ---------- throttle + headers ----------

    def _headers(self):
        return {"User-Agent": f"{self._app_id} req-{uuid.uuid4().hex[:8]}"}

    def _throttle(self):
        with NominatimGeocoder._throttle_lock:
            required_gap = random.uniform(self._min_delay_s, self._max_delay_s)
            elapsed = time.monotonic() - NominatimGeocoder._last_request_at
            if elapsed < required_gap:
                time.sleep(required_gap - elapsed)
            NominatimGeocoder._last_request_at = time.monotonic()

    def _get(self, path, params, timeout):
        self._throttle()
        merged_params = {"accept-language": "en", **params}
        return requests.get(f"{self.BASE_URL}{path}", params=merged_params, headers=self._headers(), timeout=timeout)

    # ---------- public interface ----------

    def geocode(self, place):
        """Place name -> coordinates. Raises ValueError if no match."""
        resp = self._get("/search", {"q": place, "format": "json", "limit": 1}, timeout=10)
        resp.raise_for_status()
        results = resp.json()
        if not results:
            raise ValueError(f"No match for '{place}'")

        return Coordinates(lat=float(results[0]["lat"]), lng=float(results[0]["lon"]))

    def reverse_geocode(self, coords):
        """Coordinates -> a short place name (city/town/county/state)."""
        resp = self._get("/reverse", {"lat": coords.lat, "lon": coords.lng, "format": "json"}, timeout=10)
        resp.raise_for_status()
        address = resp.json().get("address", {})
        return address.get("city") or address.get("town") or address.get("county") or address.get("state") or "Unknown"

    def reverse_geocode_city(self, coords):
        """City-tier name only - None if this point isn't in a city."""
        resp = self._get("/reverse", {"lat": coords.lat, "lon": coords.lng, "format": "json", "addressdetails": 1}, timeout=10)
        resp.raise_for_status()
        return resp.json().get("address", {}).get("city")

    # Nominatim's own classes for a real settlement/administrative area,
    # as opposed to a street address, shop, or other point of interest.
    _GEOGRAPHIC_CLASSES = {"place", "boundary"}

    def search_places(self, query, limit=5):
        """Candidate places for a live autocomplete dropdown. Best-effort
        - returns [] on a too-short query or a provider error."""
        q = (query or "").strip()
        if not q:
            return []

        local_matches = self._local_index.search(q, limit)
        if local_matches:
            places = []
            for entry in local_matches:
                places.append(Place(**_place_dict(entry)))
            return places

        if len(q) < 2:
            return []

        try:
            resp = self._get("/search", {"q": q, "format": "json", "addressdetails": 1, "limit": min(limit * 3, 20)}, timeout=5)
            resp.raise_for_status()
            raw_results = resp.json()

            geographic = []
            for r in raw_results:
                if r.get("class") in self._GEOGRAPHIC_CLASSES:
                    geographic.append(r)

            entries = []
            for r in geographic:
                provider_id = f"{r['osm_type']}:{r['osm_id']}" if r.get("osm_type") and r.get("osm_id") else None
                entries.append(_place_entry(
                    r["display_name"], float(r["lat"]), float(r["lon"]), r.get("type", ""),
                    provider_id=provider_id, label=_short_label(r.get("address") or {}),
                ))

            # Two Nominatim entities can share the same shortened label -
            # collapse those before either public results or the index see them.
            seen_labels = set()
            deduped_entries = []
            for entry in entries:
                if entry["label"] in seen_labels:
                    continue
                seen_labels.add(entry["label"])
                deduped_entries.append(entry)
            entries = deduped_entries

            self._local_index.add(entries)

            places = []
            for entry in entries[:limit]:
                places.append(Place(**_place_dict(entry)))
            return places
        except requests.RequestException:
            return []


def create_geocoder():
    """The one place that decides which Geocoder implementation this
    process talks to."""
    return NominatimGeocoder()
