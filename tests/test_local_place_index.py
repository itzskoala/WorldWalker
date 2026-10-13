# tests/test_local_place_index.py
# LocalPlaceIndex - the in-memory prefix index NominatimGeocoder.
# search_places() checks before ever touching Nominatim (see
# tests/test_geocoder.py for that integration). Pure unit tests: no
# network, no NominatimGeocoder instance, just the index itself.

from travel_logic.geocoder import LocalPlaceIndex, _place_entry

FARGO = _place_entry("Fargo, North Dakota, United States", 46.8772, -96.7898, "city")
FAIRBANKS = _place_entry("Fairbanks, Alaska, United States", 64.8378, -147.7164, "city")
FLAGSTAFF = _place_entry("Flagstaff, Arizona, United States", 35.1983, -111.6513, "city")
FRESNO = _place_entry("Fresno, California, United States", 36.7378, -119.7871, "city")
CHICAGO = _place_entry("Chicago, Illinois, United States", 41.8781, -87.6298, "city")


def test_a_single_letter_matches_every_known_place_with_that_initial():
    index = LocalPlaceIndex([FARGO, FAIRBANKS, FLAGSTAFF, FRESNO, CHICAGO])
    names = {entry["primary"] for entry in index.search("F", limit=10)}
    assert names == {"Fargo", "Fairbanks", "Flagstaff", "Fresno"}
    # Chicago doesn't start with "F" - the index isn't just returning
    # everything it has.
    assert "Chicago" not in names


def test_matching_is_case_insensitive():
    index = LocalPlaceIndex([FARGO])
    assert index.search("f", limit=10)[0]["primary"] == "Fargo"
    assert index.search("FARGO", limit=10)[0]["primary"] == "Fargo"


def test_a_longer_prefix_narrows_the_results():
    index = LocalPlaceIndex([FARGO, FAIRBANKS, FLAGSTAFF, FRESNO])
    assert {e["primary"] for e in index.search("Fa", limit=10)} == {"Fargo", "Fairbanks"}
    assert {e["primary"] for e in index.search("Far", limit=10)} == {"Fargo"}
    assert {e["primary"] for e in index.search("Fl", limit=10)} == {"Flagstaff"}


def test_search_respects_the_limit():
    index = LocalPlaceIndex([FARGO, FAIRBANKS, FLAGSTAFF, FRESNO])
    assert len(index.search("F", limit=2)) == 2


def test_search_returns_nothing_for_an_unknown_prefix():
    index = LocalPlaceIndex([FARGO])
    assert index.search("Zzz", limit=10) == []


def test_search_returns_nothing_for_an_empty_query():
    index = LocalPlaceIndex([FARGO])
    assert index.search("", limit=10) == []
    assert index.search("   ", limit=10) == []


def test_matches_include_coordinates():
    index = LocalPlaceIndex([FARGO])
    result = index.search("Fargo", limit=10)[0]
    assert (result["lat"], result["lng"]) == (46.8772, -96.7898)


def test_add_upserts_by_rounded_coordinates_not_duplicating():
    # Requirement #9: the same real place, added twice (e.g. seeded, then
    # later re-discovered via a live Nominatim search), must not become
    # two entries.
    index = LocalPlaceIndex([FARGO])
    assert len(index.search("Fargo", limit=10)) == 1

    same_place_again = _place_entry("Fargo, Cass County, North Dakota, United States", 46.8772, -96.7898, "city")
    index.add([same_place_again])

    results = index.search("Fargo", limit=10)
    assert len(results) == 1
    # The newer, richer display_name replaced the seed's simpler one -
    # add() upserts, it doesn't just no-op on a duplicate.
    assert results[0]["display_name"] == "Fargo, Cass County, North Dakota, United States"


def test_add_treats_coordinates_within_rounding_precision_as_the_same_place():
    # Same ~11m/4-decimal rounding NominatimGeocoder._cache_key_for_coords
    # already uses - two lookups of the same real place rarely return
    # bit-identical floats.
    index = LocalPlaceIndex([FARGO])
    almost_same = _place_entry("Fargo, North Dakota, United States", 46.87721, -96.78981, "city")
    index.add([almost_same])
    assert len(index.search("Fargo", limit=10)) == 1


def test_add_of_a_genuinely_different_place_does_not_overwrite_anything():
    index = LocalPlaceIndex([FARGO])
    index.add([FAIRBANKS])
    assert {e["primary"] for e in index.search("Fa", limit=10)} == {"Fargo", "Fairbanks"}
