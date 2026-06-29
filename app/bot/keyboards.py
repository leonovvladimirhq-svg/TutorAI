"""Инлайн-клавиатуры."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot import texts
from app.db.models import Student


def consent_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_CONSENT_ACCEPT, callback_data="consent:accept")
    kb.button(text=texts.BTN_CONSENT_DECLINE, callback_data="consent:decline")
    kb.adjust(1)
    return kb.as_markup()


def profile_choice_kb(profiles: list[Student]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in profiles:
        kb.button(text=p.profile_label, callback_data=f"profile:{p.id}")
    kb.adjust(1)
    return kb.as_markup()


def main_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_PROFILING, callback_data="menu:profiling")
    kb.button(text=texts.BTN_GOALS, callback_data="menu:goals")
    kb.button(text=texts.BTN_PROFILE, callback_data="menu:profile")
    kb.adjust(1)
    return kb.as_markup()


def home_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_HOME, callback_data="menu:home")
    return kb.as_markup()


def candidate_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_CONFIRM, callback_data="cand:confirm")
    kb.button(text=texts.BTN_CORRECT, callback_data="cand:correct")
    kb.button(text=texts.BTN_SKIP, callback_data="cand:skip")
    kb.adjust(3)
    return kb.as_markup()


def goals_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_GOAL_NEW, callback_data="goals:new")
    kb.button(text=texts.BTN_HOME, callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()


def goal_templates_kb(templates: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for i, t in enumerate(templates):
        kb.button(text=t["title"], callback_data=f"goalnew:{i}")
    kb.button(text=texts.BTN_GOAL_OWN, callback_data="goalnew:own")
    kb.button(text=texts.BTN_HOME, callback_data="menu:home")
    kb.adjust(1)
    return kb.as_markup()


def goal_draft_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_GOAL_SAVE, callback_data="goaldraft:save")
    kb.button(text=texts.BTN_GOAL_EDIT, callback_data="goaldraft:edit")
    kb.button(text=texts.BTN_GOAL_CANCEL, callback_data="goaldraft:cancel")
    kb.adjust(3)
    return kb.as_markup()
