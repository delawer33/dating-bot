from shared.geo.distance import haversine_km


def test_haversine_paris_lyon_order_of_magnitude() -> None:
    # Paris ~ (48.8566, 2.3522), Lyon ~ (45.7640, 4.8357) — ~400 km
    d = haversine_km(48.8566, 2.3522, 45.7640, 4.8357)
    assert 350 < d < 500
