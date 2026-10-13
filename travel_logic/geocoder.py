#geocoder.py
# Place name <-> coordinates. ABC so the provider (Nominatim now, Google
# Maps later) can be swapped without touching callers.

import json
import math
import os
import random
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import requests
from dotenv import load_dotenv

from travel_logic.coordinates import Coordinates

load_dotenv()

_CACHE_MISS = object()


def _is_valid_place_dict(d: object) -> bool:
    """Whether a single cached search_places() entry is well-formed and
    usable: the current {"value", "primary", "secondary", "lat", "lng"}
    shape (not an older cache format - see _is_valid_search_result_cache()
    for why that alone was never enough to trust), non-blank display
    text, and real, in-range coordinates. A `bool` is deliberately
    rejected for lat/lng even though Python treats it as an `int`
    subtype - `True`/`False` are never a real coordinate."""
    if not isinstance(d, dict):
        return False
    if not all(k in d for k in ("value", "primary", "secondary", "lat", "lng")):
        return False
    if not isinstance(d["value"], str) or not d["value"].strip():
        return False
    if not isinstance(d["primary"], str) or not d["primary"].strip():
        return False
    if not isinstance(d["secondary"], str):
        return False
    lat, lng = d["lat"], d["lng"]
    if isinstance(lat, bool) or isinstance(lng, bool):
        return False
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return False
    if not (math.isfinite(lat) and math.isfinite(lng)):
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0


def _is_valid_search_result_cache(cached: object) -> bool:
    """Whether a cached search_places() value is a non-empty list of
    well-formed place entries (see _is_valid_place_dict()) - replaces the
    older, looser _is_search_result_cache() shape check, which only
    confirmed "a list of dicts with a 'value' key." That let three kinds
    of bad entries sit in data/geocode_cache.json forever, indistinguishable
    from a real answer: a pre-dict-format entry from an older cache
    version (still missing "value" entirely, still caught here), a
    well-shaped but nonsensical one (blank text, out-of-range or
    non-numeric coordinates), and an empty list - a "found nothing"
    answer from a transient hiccup or an overly strict filter, cached as
    if it were a confirmed, permanent fact. All three are now treated as
    a cache miss on read (NominatimGeocoder.search_places() evicts and
    retries) and are never written in the first place (search_places()
    only calls _cache_set() when this returns True for the result)."""
    return isinstance(cached, list) and len(cached) > 0 and all(_is_valid_place_dict(item) for item in cached)


def _place_dict(entry: dict) -> dict:
    """One LocalPlaceIndex entry -> the plain, JSON-serializable dict
    search_places() actually caches to disk and returns - see Place's own
    docstring for the normalized {value, primary, secondary, lat, lng}
    shape this mirrors. Kept as a plain dict (not a Place instance)
    specifically because it round-trips through data/geocode_cache.json;
    search_places() wraps it in Place right before handing it back."""
    return {"value": entry["label"], "primary": entry["primary"], "secondary": entry["secondary"], "lat": entry["lat"], "lng": entry["lng"]}


def _split_display_name(display_name: str) -> tuple[str, str]:
    """"Fargo, Cass County, North Dakota, United States" -> ("Fargo",
    "Cass County, North Dakota, United States") - guaranteed ", "
    throughout regardless of the source string's own comma spacing. Same
    normalization app.py's _place_suggestion() does for the HTTP layer;
    duplicated (not imported) rather than shared, since travel_logic
    doesn't depend on app.py and this is a two-line function."""
    parts = [part.strip() for part in display_name.split(",") if part.strip()]
    primary = parts[0] if parts else display_name
    return primary, ", ".join(parts[1:])


def _short_label(address: dict) -> Optional[str]:
    """Nominatim's structured per-result address (present when the
    request includes addressdetails=1 - see search_places()) -> a
    concise "City, State" (US) or "City, Region, Country" (everyone
    else) label - e.g. {"city": "Ord", "county": "Valley County",
    "state": "Nebraska", "postcode": "68862", "country": "United States",
    "country_code": "us"} -> "Ord, Nebraska".

    General-purpose by construction, not a list of known cities/counties
    to strip: it reads Nominatim's own semantic address levels
    (city/town/village, state, country, ...) rather than pattern-matching
    the flat display_name string, so it produces the same shape of
    answer for any real result, including ones this file has never seen
    before. For a US result, county/postcode/"United States" are dropped
    entirely once there's a city or state to anchor the label on - a US
    "City, State" label never needs them. Returns None when the address
    has too little structured data to build a sensible short label at
    all (rare - a genuinely obscure result) - callers fall back to the
    original, full display_name in that case."""
    city = address.get("city") or address.get("town") or address.get("village") or address.get("municipality")
    region = address.get("state") or address.get("state_district") or address.get("region") or address.get("province")
    country = address.get("country")

    if (address.get("country_code") or "").lower() == "us":
        if city and region:
            return f"{city}, {region}"
        return city or region or None

    parts = [part for part in (city, region, country) if part]
    return ", ".join(parts) if parts else None


def _place_entry(
    display_name: str, lat: float, lng: float, place_type: str, provider_id: Optional[str] = None,
    label: Optional[str] = None,
) -> dict:
    """One LocalPlaceIndex entry - see its class docstring for the shape
    and why each field exists. `display_name` is Nominatim's original,
    full result string, kept for reference even though nothing shows or
    matches against it directly. `label` is the shortened text actually
    shown (the dropdown, and what a selection resolves to) and what
    `primary`/`secondary` (and therefore LocalPlaceIndex.search()'s name
    matching) are derived from - see _short_label(). Defaults to
    `display_name` unshortened when the caller has no shorter one to
    offer (e.g. a caller that never had structured address data to work
    from)."""
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
    """A process-local, in-memory prefix index of known places, grown by
    every real Nominatim search that finds a new geographic result (see
    NominatimGeocoder.search_places()). No hand-picked city list: a
    fresh checkout starts with an empty index and grows purely from real
    usage - a fixed roster of "well-known" places doesn't scale and
    doesn't belong hardcoded into this file. Exists so typing "F"/"Fa"/
    "Fargo" (or any prefix of a name this process has already seen)
    answers instantly, in-process, with zero network call and without
    spending any of the Nominatim throttle's budget - not a replacement
    for Nominatim's real coverage, just a fast path for what's already
    known.

    Keyed by rounded (lat, lng) - same ~11m/4-decimal convention
    NominatimGeocoder._cache_key_for_coords() already uses - so
    re-discovering the same real place (from two different queries that
    both eventually resolve to it) upserts one entry instead of
    accumulating duplicates.

    Deliberately simple and self-contained: swapping in a dedicated
    autocomplete provider later means replacing this one class, not
    touching search_places()'s calling convention."""

    def __init__(self, seed: list[dict]):
        self._entries: dict[str, dict] = {}
        self.add(seed)

    def add(self, entries: list[dict]) -> None:
        for entry in entries:
            key = f"{round(entry['lat'], 4)},{round(entry['lng'], 4)}"
            self._entries[key] = entry

    def search(self, query: str, limit: int) -> list[dict]:
        q = query.strip().lower()
        if not q:
            return []
        matches = [entry for entry in self._entries.values() if entry["primary"].lower().startswith(q)]
        # Shortest/alphabetical first - deterministic, and a shorter name
        # starting with the same prefix is usually the more exact match
        # ("Fargo" before "Fargo County", if that ever gets indexed).
        matches.sort(key=lambda entry: (len(entry["primary"]), entry["primary"]))
        # Two entries can show the same label without being the same
        # dict - e.g. two separately-indexed results that both shortened
        # to the same "City, State" label. Keep the first (already
        # sorted above) and drop the rest, the same way search_places()
        # dedupes Nominatim's own results by label.
        seen_labels = set()
        deduped = []
        for entry in matches:
            if entry["label"] in seen_labels:
                continue
            seen_labels.add(entry["label"])
            deduped.append(entry)
        return deduped[:limit]


@dataclass(frozen=True)
class Place:
    """One geocoded search candidate, in the one normalized shape every
    caller agrees on - app.py's HTTP layer passes this straight through
    as JSON, and the field names match frontend/src/types/trip.ts's own
    PlaceSuggestion type exactly, so no reshaping happens there either.

    This is the seam a future provider (Google Places, say) implements
    against instead of its own result shape leaking past this module:
    `value`/`primary`/`secondary` are already split into a bold/muted
    two-line row (CreatePage.tsx's autocomplete dropdown) by whichever
    Geocoder produced this - Nominatim's comma-joined display_name today,
    something else entirely for a different provider - not re-derived by
    guessing at formatting further up the stack. See NominatimGeocoder's
    _split_display_name()/_short_label() for where this one computes it."""

    value: str
    primary: str
    secondary: str
    lat: float
    lng: float


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
    def search_places(self, query: str, limit: int = 5) -> List[Place]:
        """Candidate places for a live autocomplete dropdown - e.g. "ariz"
        -> [Place(value="Arizona, United States", primary="Arizona",
        secondary="United States", lat=..., lng=...), ...]. Coordinates
        are returned alongside the name so a caller can resolve/store a
        selection without a second geocode() round trip. Best-effort:
        returns [] on a too-short query or a provider error rather than
        raising - callers are typing UIs, not journey-starting flows
        (that's still geocode(), which does raise)."""


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
    per-instance. search_places()'s LocalPlaceIndex is shared the same
    way and for the same reason - see _local_index below."""

    BASE_URL = "https://nominatim.openstreetmap.org"
    DEFAULT_CACHE_PATH = Path("data/geocode_cache.json")

    _throttle_lock = threading.Lock()
    _last_request_at = 0.0
    # Shared across every NominatimGeocoder instance in this process, not
    # per-instance - otherwise app.py's and core/facade.py's separate
    # instances would each grow their own index from what the other one
    # already found, the exact "two independent caches" gap the file
    # cache above has (each instance loads its own copy of
    # data/geocode_cache.json into memory and never sees what the other
    # writes). Starts empty - no hardcoded city list - and grows purely
    # from real Nominatim results, see LocalPlaceIndex's own docstring.
    _local_index = LocalPlaceIndex([])

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

    def _cache_evict(self, key: str) -> None:
        """Removes a bad cache entry rather than just ignoring it in
        memory - without this, a stale/invalid entry nobody happens to
        re-query would sit in data/geocode_cache.json forever, and a
        process that failed to re-fetch (e.g. search_places()'s Nominatim
        call also failing right after eviction) would otherwise leave it
        looking untouched on disk instead of genuinely gone."""
        if key in self._cache:
            del self._cache[key]
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
        # Applied here, once, rather than per call site - every Nominatim
        # request this class makes (geocode, reverse_geocode,
        # reverse_geocode_city, search_places) goes through _get(), so
        # this covers all of them. Without it Nominatim defaults to
        # whatever language the result's own locale uses (confirmed
        # live: "München, Bayern, Deutschland" instead of "Munich,
        # Bavaria, Germany", "京都市, 京都府, 日本" instead of "Kyoto,
        # Kyoto Prefecture, Japan") - not a bug in _short_label() or
        # anything else here, just Nominatim's own default with no
        # language requested. `**params` after the default means a
        # caller could still override it by passing its own
        # "accept-language" key, though nothing here does that today.
        merged_params = {"accept-language": "en", **params}
        return requests.get(f"{self.BASE_URL}{path}", params=merged_params, headers=self._headers(), timeout=timeout)

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

    # Nominatim's own class for a real settlement/administrative area
    # (city, town, village, state, country, ...) as opposed to a street
    # address, shop, or other point of interest - see
    # https://nominatim.org/release-docs/latest/customize/Ranking/#search-rank.
    # search_places() is a geographic-place picker (Where From/Where To),
    # not a general address search, so results outside these two classes
    # are dropped rather than shown.
    _GEOGRAPHIC_CLASSES = {"place", "boundary"}

    def search_places(self, query: str, limit: int = 5) -> List[Place]:
        # None shows up for real: a UI Dropdown fires its "typing" event
        # with an empty/None value on focus, before any character is
        # typed - skip it the same as a too-short/empty query, not an
        # error, same as always. Checked before the local index too -
        # there's nothing to prefix-match against an empty string.
        q = (query or "").strip()
        if not q:
            return []

        # The local index first, on every call, regardless of length - a
        # single character ("F") is exactly the case this exists for (see
        # LocalPlaceIndex). Any non-empty hit here is "sufficient": no
        # Nominatim request, no throttle spent, no exact-match file-cache
        # lookup even attempted. Deliberately not requiring a full page of
        # `limit` local matches before trusting them - with a small seed/
        # grown index that would mean this path almost never fires.
        local_matches = self._local_index.search(q, limit)
        if local_matches:
            return [Place(**_place_dict(e)) for e in local_matches]

        # Below this point is the existing Nominatim path, untouched -
        # still gated at 2 characters (a single unknown letter isn't worth
        # a real Nominatim call), still throttled, still file-cached.
        if len(q) < 2:
            return []

        key = f"search:{q.lower()}:{limit}"
        cached = self._cache_get(key)
        # A cache entry can be bad in a few ways by now: the pre-dict
        # format search_places() used to return (earlier formats used
        # "display_name" instead of "value", and the very first one was
        # plain display-name strings - confirmed live: a 500 on every
        # query whose result was cached under an old format), a
        # well-shaped but nonsensical entry (blank text, out-of-range
        # coordinates), or an empty list - a "found nothing" answer that
        # may have only been a transient hiccup, cached as if it were
        # permanent. _is_valid_search_result_cache() catches all three.
        # Evicting it (not just ignoring it) means a Nominatim failure
        # right after this doesn't leave the bad entry looking untouched
        # on disk - see _cache_evict()'s own docstring.
        if cached is not _CACHE_MISS:
            if _is_valid_search_result_cache(cached):
                return [Place(**d) for d in cached]
            self._cache_evict(key)

        try:
            # Over-fetch: the class filter below drops some raw results
            # (addresses, POIs), so asking Nominatim for exactly `limit`
            # would often hand back fewer than `limit` geographic places.
            # addressdetails=1 is what makes _short_label() possible below
            # - without it, a result's "address" breakdown is absent and
            # there's nothing to shorten from (label just falls back to
            # the full display_name in that case, not an error).
            resp = self._get(
                "/search", {"q": q, "format": "json", "addressdetails": 1, "limit": min(limit * 3, 20)}, timeout=5
            )
            resp.raise_for_status()
            raw_results = resp.json()
            geographic = [r for r in raw_results if r.get("class") in self._GEOGRAPHIC_CLASSES]
            # Built from every over-fetched geographic result (not just
            # the `limit` actually shown below) so the local index grows
            # from the full set, same as before this label-shortening
            # change - see the .add() call's own comment.
            entries = [
                _place_entry(
                    r["display_name"], float(r["lat"]), float(r["lon"]), r.get("type", ""),
                    provider_id=f"{r['osm_type']}:{r['osm_id']}" if r.get("osm_type") and r.get("osm_id") else None,
                    label=_short_label(r.get("address") or {}),
                )
                for r in geographic
            ]
            # Nominatim itself can return two genuinely different entities
            # (e.g. a place node and a boundary relation, confirmed live
            # for Santiago, Chile - same name, ~50m apart, real distinct
            # osm_ids) whose *labels* are identical even before any
            # shortening - a real result, but indistinguishable to the
            # user in the dropdown, and worth collapsing regardless of
            # which underlying entity happened to rank first. Deduped
            # here (by the label actually shown), before either the
            # public results or the local index see them - a coordinate-
            # rounding dedup alone wouldn't catch this pair; they're too
            # far apart for that.
            seen_labels = set()
            deduped_entries = []
            for entry in entries:
                if entry["label"] in seen_labels:
                    continue
                seen_labels.add(entry["label"])
                deduped_entries.append(entry)
            entries = deduped_entries
            result_dicts = [_place_dict(e) for e in entries[:limit]]
            # Only a genuinely usable answer gets written to disk - an
            # empty list (nothing matched, or everything got filtered out
            # above) is never cached as if it were a confirmed, permanent
            # "no results," so the next identical query gets a real retry
            # instead of trusting a possibly-transient empty answer.
            if _is_valid_search_result_cache(result_dicts):
                self._cache_set(key, result_dicts)
            # Grows the local index from this real lookup - see
            # LocalPlaceIndex's docstring and requirement #5. osm_type +
            # osm_id (present on every Nominatim /search result) identify
            # the real-world place itself, independent of Nominatim's own
            # DB internals - kept as provider_id for a future dedicated
            # autocomplete provider to key off of, though LocalPlaceIndex.
            # add() itself dedupes by coordinates, not this id.
            self._local_index.add(entries)
            return [Place(**d) for d in result_dicts]
        except requests.RequestException:
            # A transient network failure (timeout, DNS, Nominatim down,
            # ...) is never cached - there's no _cache_set() call on this
            # path, deliberately, so the very next call for this same
            # query gets a real retry instead of a permanently "failed"
            # answer.
            return []


def create_geocoder() -> Geocoder:
    """The one place that decides which Geocoder implementation this
    process actually talks to. app.py and core/facade.py both call this
    instead of constructing NominatimGeocoder() directly, so swapping
    providers later (Google Places, say) means adding that
    implementation and changing the `return` below - not touching either
    caller, both of which only ever see the Geocoder interface."""
    return NominatimGeocoder()
