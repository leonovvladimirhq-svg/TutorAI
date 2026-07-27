"""FSM-состояния бота (порт app.bot.states под maxapi)."""
from __future__ import annotations

from maxapi.context import State, StatesGroup


class Profiling(StatesGroup):
    chatting = State()


class Goals(StatesGroup):
    chatting = State()


class ProfileEdit(StatesGroup):
    waiting_value = State()


class Feedback(StatesGroup):
    waiting_comment = State()
