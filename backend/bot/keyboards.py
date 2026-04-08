from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
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
