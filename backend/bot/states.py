from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    waiting_display_name = State()
    waiting_birth_date = State()
    waiting_gender = State()
    waiting_location = State()
    waiting_photos = State()
    waiting_search_age = State()
    waiting_search_gender = State()
    waiting_search_distance = State()
    waiting_optional_bio = State()
    waiting_optional_interests = State()
    waiting_complete_confirm = State()


class SettingsStates(StatesGroup):
    profile_display_name = State()
    profile_birth_date = State()
    profile_gender = State()
    profile_location = State()
    profile_bio = State()
    profile_interests = State()
    profile_add_photo = State()
    profile_delete_photo = State()
    profile_reorder_photos = State()
    prefs_age = State()
    prefs_gender = State()
    prefs_distance = State()
