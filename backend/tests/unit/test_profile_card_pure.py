"""Pure helpers on profile_card."""

from datetime import date

from api.services.profile_card import age_on_date


def test_age_on_date_birthday_not_yet() -> None:
    assert age_on_date(date(2000, 6, 15), date(2020, 6, 14)) == 19


def test_age_on_date_birthday_today() -> None:
    assert age_on_date(date(2000, 6, 15), date(2020, 6, 15)) == 20
