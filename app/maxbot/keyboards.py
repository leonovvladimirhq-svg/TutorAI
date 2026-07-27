"""Инлайн-клавиатуры (порт app.bot.keyboards под maxapi).

aiogram: kb.button(text=, callback_data=)  →  maxapi: kb.add(CallbackButton(text=, payload=)).
callback_data == payload; строковые схемы payload сохранены 1:1, чтобы не трогать
логику разбора в обработчиках. as_markup() возвращает AttachmentButton — его кладём
в attachments=[...] при отправке.
"""
from __future__ import annotations

from maxapi.types import CallbackButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from app.bot import texts


def consent_intro_kb() -> "object":
    kb = InlineKeyboardBuilder()
    kb.add(CallbackButton(text=texts.BTN_CONSENT_READ, payload="consent:read"))
    return kb.as_markup()


def consent_kb() -> "object":
    kb = InlineKeyboardBuilder()
    kb.add(CallbackButton(text=texts.BTN_CONSENT_FULLTEXT, payload="consent:fulltext"))
    kb.add(CallbackButton(text=texts.BTN_CONSENT_ACCEPT, payload="consent:accept"))
    kb.add(CallbackButton(text=texts.BTN_CONSENT_DECLINE, payload="consent:decline"))
    kb.adjust(1)
    return kb.as_markup()


def forget_me_confirm_kb() -> "object":
    kb = InlineKeyboardBuilder()
    kb.add(CallbackButton(text=texts.BTN_FORGET_YES, payload="forget:yes"))
    kb.add(CallbackButton(text=texts.BTN_FORGET_NO, payload="forget:no"))
    kb.adjust(1)
    return kb.as_markup()


def feedback_rating_kb(context: str = "menu", ref_id: int | None = None) -> "object":
    """Кнопки 👍/👎. payload: fb:<up|down>:<context>:<ref_id or ''>."""
    ref = str(ref_id) if ref_id is not None else ""
    kb = InlineKeyboardBuilder()
    kb.add(CallbackButton(text=texts.BTN_FB_UP, payload=f"fb:up:{context}:{ref}"))
    kb.add(CallbackButton(text=texts.BTN_FB_DOWN, payload=f"fb:down:{context}:{ref}"))
    kb.adjust(2)
    return kb.as_markup()


def feedback_skip_kb() -> "object":
    kb = InlineKeyboardBuilder()
    kb.add(CallbackButton(text=texts.BTN_FB_SKIP, payload="fb:skip"))
    return kb.as_markup()


def main_menu_kb() -> "object":
    kb = InlineKeyboardBuilder()
    kb.add(CallbackButton(text=texts.BTN_PROFILING, payload="menu:profiling"))
    kb.add(CallbackButton(text=texts.BTN_GOALS, payload="menu:goals"))
    kb.add(CallbackButton(text=texts.BTN_PROFILE, payload="menu:profile"))
    kb.add(CallbackButton(text=texts.BTN_FEEDBACK, payload="menu:feedback"))
    kb.adjust(1)
    return kb.as_markup()


def home_kb() -> "object":
    kb = InlineKeyboardBuilder()
    kb.add(CallbackButton(text=texts.BTN_HOME, payload="menu:home"))
    return kb.as_markup()


def candidate_kb() -> "object":
    kb = InlineKeyboardBuilder()
    kb.add(CallbackButton(text=texts.BTN_CONFIRM, payload="cand:confirm"))
    kb.add(CallbackButton(text=texts.BTN_CORRECT, payload="cand:correct"))
    kb.add(CallbackButton(text=texts.BTN_SKIP, payload="cand:skip"))
    kb.adjust(3)
    return kb.as_markup()


def goals_menu_kb() -> "object":
    kb = InlineKeyboardBuilder()
    kb.add(CallbackButton(text=texts.BTN_GOAL_NEW, payload="goals:new"))
    kb.add(CallbackButton(text=texts.BTN_HOME, payload="menu:home"))
    kb.adjust(1)
    return kb.as_markup()


def goal_templates_kb(templates: list[dict]) -> "object":
    kb = InlineKeyboardBuilder()
    for i, t in enumerate(templates):
        kb.add(CallbackButton(text=t["title"], payload=f"goalnew:{i}"))
    kb.add(CallbackButton(text=texts.BTN_GOAL_OWN, payload="goalnew:own"))
    kb.add(CallbackButton(text=texts.BTN_HOME, payload="menu:home"))
    kb.adjust(1)
    return kb.as_markup()


def goal_draft_kb() -> "object":
    kb = InlineKeyboardBuilder()
    kb.add(CallbackButton(text=texts.BTN_GOAL_SAVE, payload="goaldraft:save"))
    kb.add(CallbackButton(text=texts.BTN_GOAL_EDIT, payload="goaldraft:edit"))
    kb.add(CallbackButton(text=texts.BTN_GOAL_CANCEL, payload="goaldraft:cancel"))
    kb.adjust(3)
    return kb.as_markup()


def profile_view_kb() -> "object":
    kb = InlineKeyboardBuilder()
    kb.add(CallbackButton(text=texts.BTN_EDIT, payload="profile:edit"))
    kb.add(CallbackButton(text=texts.BTN_HOME, payload="menu:home"))
    kb.adjust(1)
    return kb.as_markup()


def profile_edit_list_kb(attributes) -> "object":
    from app.domain.profile_schema import PROFILE_BLOCKS_BY_KEY

    kb = InlineKeyboardBuilder()
    for attr in attributes:
        title = PROFILE_BLOCKS_BY_KEY[attr.block].title if attr.block in PROFILE_BLOCKS_BY_KEY else attr.block
        label = f"{title}: {attr.value}"
        kb.add(CallbackButton(text=label[:60], payload=f"attredit:{attr.id}"))
    kb.add(CallbackButton(text=texts.BTN_BACK, payload="menu:profile"))
    kb.adjust(1)
    return kb.as_markup()
