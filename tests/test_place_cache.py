# tests/test_place_cache.py
# PlaceCache's cache-aside logic (travel_logic/place_cache.py): Redis
# first, Postgres on a miss, Redis gets backfilled from whatever Postgres
# answered. Runs against real Postgres (see conftest.py) with a fake
# Redis double - no real Redis server needed for these.

from backend.database.models import PlaceRecord
from backend.travel_logic.dataclasses.coordinates import Coordinates
from backend.travel_logic.dataclasses.place import Place
from backend.travel_logic.place_cache import PlaceCache


class FixedSession:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class FakeRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, ttl, value):
        self.values[key] = value


FARGO = {"primary": "Fargo", "secondary": "North Dakota, United States", "lat": 46.8772, "lng": -96.7898, "provider_id": "node:1"}


def place_cache(db_session):
    return PlaceCache(FakeRedis(), FixedSession(db_session))


def test_search_returns_nothing_when_both_cache_and_db_are_empty(db_session):
    cache = place_cache(db_session)
    assert cache.search("fargo", 5) == []


def test_store_then_search_finds_it_via_postgres(db_session):
    cache = place_cache(db_session)
    cache.store([FARGO])

    result = cache.search("far", 5)

    assert result == [Place(value="Fargo, North Dakota, United States", primary="Fargo", secondary="North Dakota, United States", lat=46.8772, lng=-96.7898)]


def test_search_hits_redis_on_the_second_call_without_touching_postgres(db_session):
    cache = place_cache(db_session)
    cache.store([FARGO])
    cache.search("far", 5)  # warms the redis entry

    db_session.query(PlaceRecord).delete()
    db_session.flush()

    result = cache.search("far", 5)
    assert len(result) == 1


def test_store_does_not_duplicate_the_same_provider_id(db_session):
    cache = place_cache(db_session)
    cache.store([FARGO])
    cache.store([FARGO])

    assert db_session.query(PlaceRecord).count() == 1


def test_store_falls_back_to_a_coordinate_key_when_there_is_no_provider_id(db_session):
    cache = place_cache(db_session)
    entry = {**FARGO, "provider_id": None}
    cache.store([entry])
    cache.store([entry])

    assert db_session.query(PlaceRecord).count() == 1


def test_reverse_cache_aside(db_session):
    cache = place_cache(db_session)
    coords = Coordinates(lat=46.8772, lng=-96.7898)

    assert cache.reverse(coords) is None
    cache.cache_reverse(coords, "Fargo")
    assert cache.reverse(coords) == "Fargo"
