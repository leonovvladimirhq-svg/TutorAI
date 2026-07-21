"""FSM-состояния бота."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Profiling(StatesGroup):
    chatting = State()


class Goals(StatesGroup):
    chatting = State()


class ProfileEdit(StatesGroup):
    waiting_value = State()


class Feedback(StatesGroup):
    waiting_comment = State()
