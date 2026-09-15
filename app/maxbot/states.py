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


class MentorReject(StatesGroup):
    waiting_reason = State()


class Reflection(StatesGroup):
    """Подведение итогов по целям: ответы на коучинговые вопросы и закономерности."""
    outcome = State()          # ждём кнопку «получилось?»
    answering = State()        # отвечает на коучинговые вопросы
    irrelevant_note = State()  # цель неактуальна — почему
    patterns = State()         # свои закономерности (до сводки ИИ)
