# tests/test_short_label.py
# _short_label() - Nominatim's structured per-result "address" breakdown
# (addressdetails=1) -> a concise "City, State" (US) or "City, Region,
# Country" label. General-purpose by construction: every case here reads
# real Nominatim address shapes (captured live while building this), not
# a hardcoded list of cities/counties to special-case.

from travel_logic.geocoder import _short_label

# The real address Nominatim returns for "Ord, Nebraska" (addressdetails=1),
# captured live - the exact example this feature was requested for.
_ORD_NEBRASKA = {
    "city": "Ord",
    "county": "Valley County",
    "state": "Nebraska",
    "ISO3166-2-lvl4": "US-NE",
    "postcode": "68862",
    "country": "United States",
    "country_code": "us",
}

# The real address Nominatim returns for "Paris, France" (addressdetails=1).
_PARIS_FRANCE = {
    "city": "Paris",
    "ISO3166-2-lvl6": "FR-75C",
    "state": "Île-de-France",
    "ISO3166-2-lvl4": "FR-IDF",
    "region": "France métropolitaine",
    "country": "France",
    "country_code": "fr",
}


def test_us_result_becomes_city_comma_state():
    assert _short_label(_ORD_NEBRASKA) == "Ord, Nebraska"


def test_us_result_drops_county_postcode_and_country_name():
    label = _short_label(_ORD_NEBRASKA)
    assert "Valley County" not in label
    assert "68862" not in label
    assert "United States" not in label


def test_second_reported_example_fargo():
    address = {
        "city": "Fargo", "county": "Cass County", "state": "North Dakota",
        "postcode": "58102", "country": "United States", "country_code": "us",
    }
    assert _short_label(address) == "Fargo, North Dakota"


def test_us_result_with_only_a_city_falls_back_to_the_city_alone():
    address = {"city": "Ord", "country": "United States", "country_code": "us"}
    assert _short_label(address) == "Ord"


def test_us_result_with_only_a_state_falls_back_to_the_state_alone():
    # e.g. searching "Nebraska" itself - the result IS the state, no city
    # level exists to attach to it.
    address = {"state": "Nebraska", "country": "United States", "country_code": "us"}
    assert _short_label(address) == "Nebraska"


def test_international_result_is_city_region_country():
    assert _short_label(_PARIS_FRANCE) == "Paris, Île-de-France, France"


def test_international_result_falls_back_through_region_field_names():
    # Not every country's Nominatim data populates "state" - this proves
    # the fallback chain (state -> state_district -> region -> province)
    # actually works, not just the common "state" case.
    for region_key in ("state", "state_district", "region", "province"):
        address = {"city": "Testville", "country": "Testland", "country_code": "zz", region_key: "Test Region"}
        assert _short_label(address) == "Testville, Test Region, Testland"


def test_international_result_with_only_a_country_falls_back_to_the_country_alone():
    # e.g. searching "France" itself.
    assert _short_label({"country": "France", "country_code": "fr"}) == "France"


def test_empty_address_returns_none():
    # Caller (search_places()) falls back to the original, full
    # display_name in this case - not an empty/broken label.
    assert _short_label({}) is None


def test_address_with_only_unrecognized_fields_returns_none():
    assert _short_label({"neighbourhood": "Somewhere", "road": "Main St"}) is None
