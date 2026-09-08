#geocoder.py
# Place name <-> coordinates. ABC so the provider (Nominatim now, Google
# Maps later) can be swapped without touching callers.

from abc import ABC, abstractmethod
from typing import Optional
import requests
from travel_logic.coordinates import Coordinates


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


class NominatimGeocoder(Geocoder):
    BASE_URL = "https://nominatim.openstreetmap.org"
    # Nominatim's usage policy wants a real contact in the User-Agent for
    # anything beyond light dev use - swap in your own before real traffic.
    HEADERS = {"User-Agent": "WorldWalker-MVP/1.0"}

    def geocode(self, place: str) -> Coordinates:
        resp = requests.get(
            f"{self.BASE_URL}/search",
            params={"q": place, "format": "json", "limit": 1},
            headers=self.HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            raise ValueError(f"No match for '{place}'")
        return Coordinates(lat=float(results[0]["lat"]), lng=float(results[0]["lon"]))

    def reverse_geocode(self, coords: Coordinates) -> str:
        resp = requests.get(
            f"{self.BASE_URL}/reverse",
            params={"lat": coords.lat, "lon": coords.lng, "format": "json"},
            headers=self.HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        address = resp.json().get("address", {})
        return (
            address.get("city")
            or address.get("town")
            or address.get("county")
            or address.get("state")
            or "Unknown"
        )

    def reverse_geocode_city(self, coords: Coordinates) -> Optional[str]:
        resp = requests.get(
            f"{self.BASE_URL}/reverse",
            params={"lat": coords.lat, "lon": coords.lng, "format": "json", "addressdetails": 1},
            headers=self.HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("address", {}).get("city")
