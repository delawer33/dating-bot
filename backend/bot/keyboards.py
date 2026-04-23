from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from shared.interests_taxonomy import sorted_interest_choices

# Main menu (reply keyboard) — labels must match handlers in `handlers/menu.py`.
BTN_BROWSE = "Анкеты"
BTN_MY_PROFILE = "Мой профиль"
BTN_SEARCH_PREFS = "Параметры поиска"

MAIN_MENU_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_BROWSE)],
        [KeyboardButton(text=BTN_MY_PROFILE)],
        [KeyboardButton(text=BTN_SEARCH_PREFS)],
    ],
    resize_keyboard=True,
)

# My profile submenu
BTN_PROFILE_SHOW = "Показать анкету"
BTN_PROFILE_NAME = "Имя"
BTN_PROFILE_BIRTH = "Дата рождения"
BTN_PROFILE_GENDER = "Пол"
BTN_PROFILE_LOCATION = "Город / локация"
BTN_PROFILE_BIO = "О себе"
BTN_PROFILE_INTERESTS = "Интересы"
BTN_PROFILE_ADD_PHOTO = "Добавить фото"
BTN_PROFILE_DEL_PHOTO = "Удалить фото"
BTN_PROFILE_REORDER_INFO = "Порядок фото"
BTN_INCOMING_LIKES = "Кто меня лайкнул"
BTN_REFERRAL = "Пригласить друга"
BTN_BACK_MAIN = "« В меню"
BTN_CANCEL_EDIT = "Отмена"

PROFILE_MENU_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_PROFILE_SHOW)],
        [
            KeyboardButton(text=BTN_PROFILE_NAME),
            KeyboardButton(text=BTN_PROFILE_BIRTH),
        ],
        [
            KeyboardButton(text=BTN_PROFILE_GENDER),
            KeyboardButton(text=BTN_PROFILE_LOCATION),
        ],
        [KeyboardButton(text=BTN_PROFILE_BIO), KeyboardButton(text=BTN_PROFILE_INTERESTS)],
        [
            KeyboardButton(text=BTN_PROFILE_ADD_PHOTO),
            KeyboardButton(text=BTN_PROFILE_DEL_PHOTO),
        ],
        [KeyboardButton(text=BTN_PROFILE_REORDER_INFO)],
        [KeyboardButton(text=BTN_INCOMING_LIKES)],
        [KeyboardButton(text=BTN_REFERRAL)],
        [KeyboardButton(text=BTN_BACK_MAIN)],
    ],
    resize_keyboard=True,
)

# Search preferences (settings) submenu
BTN_PREF_AGE = "Возраст анкет"
BTN_PREF_GENDER = "Пол в анкетах"
BTN_PREF_DISTANCE = "Макс. расстояние"
BTN_PREF_SHOW = "Показать параметры"

SEARCH_PREFS_MENU_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_PREF_SHOW)],
        [KeyboardButton(text=BTN_PREF_AGE), KeyboardButton(text=BTN_PREF_GENDER)],
        [KeyboardButton(text=BTN_PREF_DISTANCE)],
        [KeyboardButton(text=BTN_BACK_MAIN)],
    ],
    resize_keyboard=True,
)

GENDER_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="Мужской", callback_data="gender:male"),
            InlineKeyboardButton(text="Женский", callback_data="gender:female"),
        ],
        [
            InlineKeyboardButton(text="Небинарный", callback_data="gender:non_binary"),
            InlineKeyboardButton(text="Другой", callback_data="gender:other"),
        ],
    ]
)

LOCATION_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Поделиться геолокацией", request_location=True)]],
    resize_keyboard=True,
    one_time_keyboard=True,
)


def settings_cancel_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL_EDIT)]],
        resize_keyboard=True,
    )


def location_reply_with_cancel() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Поделиться геолокацией", request_location=True)],
            [KeyboardButton(text=BTN_CANCEL_EDIT)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def photo_delete_inline_keyboard(photos: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for p in sorted(photos, key=lambda x: int(x.get("sort_order") or 0)):
        pid = p.get("id")
        if not pid:
            continue
        so = int(p.get("sort_order") or 0)
        pid_str = str(pid)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Удалить фото №{so}",
                    callback_data=f"setphdel:{pid_str}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="setphdel:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def photo_reorder_inline_keyboard(
    order_ids: list[str],
    label_by_id: dict[str, int],
) -> InlineKeyboardMarkup:
    """order_ids: current order; label_by_id: stable 1..n per photo from session start; ↑/↓ swap neighbors."""
    rows: list[list[InlineKeyboardButton]] = []
    n = len(order_ids)
    for i in range(n):
        tag = str(label_by_id[order_ids[i]])
        label = InlineKeyboardButton(text=f" {tag} ", callback_data="setphre:nop")
        if i > 0:
            up = InlineKeyboardButton(text="↑", callback_data=f"setphre:u:{i}")
        else:
            up = InlineKeyboardButton(text=" ", callback_data="setphre:nop")
        if i < n - 1:
            down = InlineKeyboardButton(text="↓", callback_data=f"setphre:d:{i}")
        else:
            down = InlineKeyboardButton(text=" ", callback_data="setphre:nop")
        rows.append([label, up, down])
    rows.append([InlineKeyboardButton(text="Готово", callback_data="setphre:done")])
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="setphre:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

REGISTRATION_PHOTOS_NEXT = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Дальше", callback_data="registration:photos_next")],
    ]
)

REGISTRATION_COMPLETE = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Завершить регистрацию",
                callback_data="registration:complete",
            )
        ],
    ]
)

BTN_SKIP = "Пропустить"
BTN_OPTIONAL_BIO_SKIP = "Пропустить «о себе»"

OPTIONAL_BIO_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_OPTIONAL_BIO_SKIP)]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

# Search preferences during registration (reply)
BTN_PREF_ALL = "Все"
BTN_PREF_MEN = "Только мужчины"
BTN_PREF_WOMEN = "Только женщины"
BTN_PREF_MW = "М и Ж"

SEARCH_GENDER_REPLY = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_PREF_ALL)],
        [KeyboardButton(text=BTN_PREF_MEN), KeyboardButton(text=BTN_PREF_WOMEN)],
        [KeyboardButton(text=BTN_PREF_MW)],
    ],
    resize_keyboard=True,
)


def registration_interests_keyboard(selected: frozenset[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for iid, label in sorted_interest_choices():
        mark = "✓ " if iid in selected else ""
        row.append(
            InlineKeyboardButton(
                text=f"{mark}{label}",
                callback_data=f"regint:{iid}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(text="Готово", callback_data="regint:done"),
            InlineKeyboardButton(text="Пропустить", callback_data="regint:skip"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_interests_keyboard(selected: frozenset[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for iid, label in sorted_interest_choices():
        mark = "✓ " if iid in selected else ""
        row.append(
            InlineKeyboardButton(
                text=f"{mark}{label}",
                callback_data=f"setint:{iid}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="Сохранить", callback_data="setint:done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
