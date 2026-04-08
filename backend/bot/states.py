from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    waiting_display_name = State()
    waiting_birth_date = State()
    waiting_gender = State()
    waiting_location = State()
