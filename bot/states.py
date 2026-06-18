from aiogram.fsm.state import State, StatesGroup


class OnboardingState(StatesGroup):
    age_gate = State()
    nsfw_opt_in = State()
