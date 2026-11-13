import json

from backend.database.models import PlaceRecord
from backend.travel_logic.dataclasses.place import Place

SEARCH_TTL_SECONDS = 60 * 60 * 24 * 30
SHORT_QUERY_TTL_SECONDS = 60 * 10
REVERSE_TTL_SECONDS = 60 * 60 * 24 * 30
MIN_CACHE_QUERY_LEN = 3


def place_to_dict(place):
    return {"value": place.value, "primary": place.primary, "secondary": place.secondary, "lat": place.lat, "lng": place.lng}


def record_to_place(record):
    label = f"{record.name}, {record.region}" if record.region else record.name
    return Place(value=label, primary=record.name, secondary=record.region, lat=record.lat, lng=record.lng)


def coord_key(lat, lng):
    return f"{round(lat, 3)}:{round(lng, 3)}"


class PlaceCache:

    def __init__(self, redis_client, session_factory):
        self.redis_client = redis_client
        self.session_factory = session_factory

    def search_key(self, query):
        return f"places:search:{query}"

    def reverse_key(self, coords):
        return f"places:reverse:{coord_key(coords.lat, coords.lng)}"

    def search(self, query, limit):
        q = query.strip().lower()
        if not q:
            return []

        cached = self.redis_client.get(self.search_key(q))
        if cached is not None:
            return [Place(**entry) for entry in json.loads(cached)][:limit]

        places = self.search_postgres(q, limit)
        if places:
            self.cache_search(q, places)
        return places

    def search_postgres(self, q, limit):
        with self.session_factory() as session:
            records = (
                session.query(PlaceRecord)
                .filter(PlaceRecord.search_key.like(f"{q}%"))
                .order_by(PlaceRecord.search_key)
                .limit(limit)
                .all()
            )
            return [record_to_place(record) for record in records]

    def cache_search(self, q, places):
        ttl = SEARCH_TTL_SECONDS if len(q) >= MIN_CACHE_QUERY_LEN else SHORT_QUERY_TTL_SECONDS
        payload = json.dumps([place_to_dict(place) for place in places])
        self.redis_client.setex(self.search_key(q), ttl, payload)

    def store(self, entries):
        with self.session_factory() as session:
            for entry in entries:
                provider_id = entry.get("provider_id") or f"coord:{coord_key(entry['lat'], entry['lng'])}"
                existing = session.query(PlaceRecord).filter_by(provider_id=provider_id).first()
                if existing:
                    continue
                session.add(PlaceRecord(
                    provider_id=provider_id,
                    name=entry["primary"],
                    region=entry["secondary"],
                    lat=entry["lat"],
                    lng=entry["lng"],
                    search_key=entry["primary"].strip().lower(),
                ))
            session.commit()

    def reverse(self, coords):
        return self.redis_client.get(self.reverse_key(coords))

    def cache_reverse(self, coords, place):
        self.redis_client.setex(self.reverse_key(coords), REVERSE_TTL_SECONDS, place)
