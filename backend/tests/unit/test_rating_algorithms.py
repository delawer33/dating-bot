import pytest

from api.services import rating_algorithms as ra


def test_primary_score_bounds() -> None:
    assert ra.compute_primary_score(0, False) == 0.0
    assert ra.compute_primary_score(100, False) == 1.0
    assert ra.compute_primary_score(50, False) == 0.5


def test_primary_distance_bump() -> None:
    assert ra.compute_primary_score(100, True) == 1.0
    assert ra.compute_primary_score(0, True) == pytest.approx(0.02)


def test_behavioral_cold_start() -> None:
    score, detail = ra.compute_behavioral_score(None)
    assert score == 0.32
    assert detail.get("cold_start") is True


def test_behavioral_with_likes_only() -> None:
    score, detail = ra.compute_behavioral_score(ra.BehaviorInputs(10, 0, 0))
    assert 0 < score <= 1.0
    assert detail["likes_received"] == 10


def test_referral_bonus_cap() -> None:
    b, _ = ra.compute_referral_bonus(100)
    assert b == pytest.approx(0.12)


def test_combined_clamped() -> None:
    c = ra.compute_combined(1.0, 1.0, 0.5)
    assert c == 1.0
    c2 = ra.compute_combined(0.0, 0.0, 0.0)
    assert c2 == 0.0


def test_match_order_helper() -> None:
    import uuid

    a = uuid.UUID("00000000-0000-0000-0000-000000000001")
    b = uuid.UUID("00000000-0000-0000-0000-000000000002")
    lo, hi = (a, b) if a < b else (b, a)
    assert lo == a and hi == b
