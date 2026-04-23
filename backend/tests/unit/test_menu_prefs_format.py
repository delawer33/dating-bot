from bot.handlers.menu import _format_preferences_text


def test_format_preferences_empty() -> None:
    t = _format_preferences_text(None)
    assert "параметры" in t.lower()


def test_format_preferences_full() -> None:
    text = _format_preferences_text(
        {
            "age_min": 18,
            "age_max": 35,
            "gender_preferences": ["female"],
            "max_distance_km": 50,
        }
    )
    assert "18" in text and "35" in text
    assert "female" in text
    assert "50" in text
