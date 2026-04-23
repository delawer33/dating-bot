"""Versioned rating formulas (Level 1–3) for discovery ranking."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

ALGORITHM_VERSION = "v1.0.0"

# Weights for combined score (referral_bonus added separately, then clamped).
WEIGHT_PRIMARY = 0.42
WEIGHT_BEHAVIORAL = 0.43
# Remaining mass implicitly leaves headroom for referral before clamp.

EPS = 1e-9


@dataclass(frozen=True)
class BehaviorInputs:
    likes_received: int
    skips_received: int
    matches_count: int


def compute_primary_score(completeness_score: int, has_distance_pref: bool) -> float:
    """Level 1: questionnaire completeness in [0, 1], tiny bump if distance pref set."""
    base = min(1.0, max(0.0, float(completeness_score) / 100.0))
    if has_distance_pref:
        base = min(1.0, base + 0.02)
    return base


def compute_behavioral_score(stats: BehaviorInputs | None) -> tuple[float, dict[str, Any]]:
    """Level 2: likes/skips ratio + damped engagement + matches (no dialog signal)."""
    if stats is None:
        return 0.32, {"cold_start": True}

    likes = max(0, stats.likes_received)
    skips = max(0, stats.skips_received)
    matches = max(0, stats.matches_count)
    denom = likes + skips + EPS
    like_ratio = likes / denom

    # Damp totals so veterans do not saturate the score.
    engagement = math.log1p(likes + matches * 2) / math.log1p(80.0)
    engagement = min(1.0, max(0.0, engagement))

    match_signal = math.log1p(matches) / math.log1p(25.0)
    match_signal = min(1.0, max(0.0, match_signal))

    behavioral = 0.45 * like_ratio + 0.35 * engagement + 0.20 * match_signal
    behavioral = min(1.0, max(0.0, behavioral))
    breakdown = {
        "like_ratio": like_ratio,
        "engagement": engagement,
        "match_signal": match_signal,
        "likes_received": likes,
        "skips_received": skips,
        "matches_count": matches,
    }
    return behavioral, breakdown


def compute_referral_bonus(successful_referrals: int) -> tuple[float, dict[str, Any]]:
    """Small additive bonus for users who referred others (credited at referee complete)."""
    n = max(0, successful_referrals)
    # Cap so referral cannot dominate the leaderboard.
    bonus = min(0.12, 0.03 * float(n))
    return bonus, {"successful_referrals": n}


def compute_combined(
    primary: float,
    behavioral: float,
    referral_bonus: float,
    *,
    weight_primary: float = WEIGHT_PRIMARY,
    weight_behavioral: float = WEIGHT_BEHAVIORAL,
) -> float:
    """Level 3: weighted blend + referral, clamped to [0, 1]."""
    raw = weight_primary * primary + weight_behavioral * behavioral + referral_bonus
    return min(1.0, max(0.0, raw))


def build_breakdown(
    *,
    primary: float,
    behavioral: float,
    referral_bonus: float,
    combined: float,
    behavioral_detail: dict[str, Any],
    referral_detail: dict[str, Any],
    has_distance_pref: bool,
) -> dict[str, Any]:
    return {
        "primary": primary,
        "behavioral": behavioral,
        "referral_bonus": referral_bonus,
        "combined": combined,
        "weights": {
            "primary": WEIGHT_PRIMARY,
            "behavioral": WEIGHT_BEHAVIORAL,
        },
        "has_distance_pref": has_distance_pref,
        "behavioral_detail": behavioral_detail,
        "referral_detail": referral_detail,
    }
