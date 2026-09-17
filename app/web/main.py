"""Веб-панель академического руководителя.

Позволяет управлять ролями пользователей (Telegram ID → роль) без правки БД вручную.
Вход — логин/пароль из настроек (по умолчанию academ / ABCD). Сессия — подписанный cookie.
Панель переиспользует БД и модели бота (app.db).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.db import crud
from app.db.session import AsyncSessionLocal
from app.services.roles import (
    ROLE_DESCRIPTIONS,
    ROLE_DIRECTOR,
    ROLE_LABELS,
    ROLE_MENTOR,
    ROLE_STUDENT,
    ROLES,
    is_valid_role,
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="TutorAI — панель наставника")
app.add_middleware(SessionMiddleware, secret_key=settings.web_session_secret)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


def _is_authed(request: Request) -> bool:
    return bool(request.session.get("authed"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if _is_authed(request):
        return RedirectResponse("/dashboard", status_code=303)
    return RedirectResponse("/login", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    if _is_authed(request):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if username == settings.web_admin_user and password == settings.web_admin_password:
        request.session["authed"] = True
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(
        request, "login.html", {"error": "Неверный логин или пароль"}, status_code=401
    )


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, session: AsyncSession = Depends(get_session)):
    if not _is_authed(request):
        return RedirectResponse("/login", status_code=303)
    users = await crud.list_app_users(session)
    mentors = await crud.list_mentors(session)
    goals_deadline = await crud.get_setting(session, "goals_deadline")
    reflection_deadline = await crud.get_setting(session, "reflection_deadline")
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "users": users,
            "mentors": mentors,
            "goals_deadline": goals_deadline or "",
            "reflection_deadline": reflection_deadline or "",
            "roles": ROLES,
            "role_labels": ROLE_LABELS,
            "role_descriptions": ROLE_DESCRIPTIONS,
            "notice": request.query_params.get("notice"),
            "error": request.query_params.get("error"),
        },
    )


@app.get("/feedback", response_class=HTMLResponse)
async def feedback_list(request: Request, session: AsyncSession = Depends(get_session)):
    if not _is_authed(request):
        return RedirectResponse("/login", status_code=303)
    items = await crud.list_feedback(session)
    return templates.TemplateResponse(
        request,
        "feedback.html",
        {"items": items},
    )


@app.post("/users")
async def add_user(
    request: Request,
    telegram_id: str = Form(...),
    role: str = Form(...),
    full_name: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    if not _is_authed(request):
        return RedirectResponse("/login", status_code=303)
    try:
        tg_id = int(telegram_id.strip())
    except ValueError:
        return RedirectResponse("/dashboard?error=Telegram+ID+должен+быть+числом", status_code=303)
    if not is_valid_role(role):
        return RedirectResponse("/dashboard?error=Некорректная+роль", status_code=303)
    await crud.add_app_user(session, tg_id, role, full_name.strip() or None)
    return RedirectResponse("/dashboard?notice=Сохранено", status_code=303)


@app.post("/users/{user_id}/role")
async def change_role(
    request: Request,
    user_id: int,
    role: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    if not _is_authed(request):
        return RedirectResponse("/login", status_code=303)
    if is_valid_role(role):
        await crud.set_app_user_role(session, user_id, role)
    return RedirectResponse("/dashboard?notice=Роль+обновлена", status_code=303)


@app.post("/users/{user_id}/delete")
async def delete_user(
    request: Request,
    user_id: int,
    session: AsyncSession = Depends(get_session),
):
    if not _is_authed(request):
        return RedirectResponse("/login", status_code=303)
    await crud.delete_app_user(session, user_id)
    return RedirectResponse("/dashboard?notice=Удалено", status_code=303)


# --- Модуль наставника: привязка, сроки, сводка ----------------------------

@app.post("/users/{user_id}/mentor")
async def change_mentor(
    request: Request,
    user_id: int,
    mentor_tg: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    """Закрепить наставника за студентом (пустое значение — снять)."""
    if not _is_authed(request):
        return RedirectResponse("/login", status_code=303)
    value: int | None
    try:
        value = int(mentor_tg) if mentor_tg.strip() else None
    except ValueError:
        return RedirectResponse("/dashboard?error=Некорректный+наставник", status_code=303)
    await crud.set_app_user_mentor(session, user_id, value)
    return RedirectResponse("/dashboard?notice=Наставник+обновлён", status_code=303)


@app.post("/settings")
async def save_settings(
    request: Request,
    goals_deadline: str = Form(""),
    reflection_deadline: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    """Сроки периода: подача целей и рефлексия (даты YYYY-MM-DD, пусто — снять)."""
    if not _is_authed(request):
        return RedirectResponse("/login", status_code=303)
    await crud.set_setting(session, "goals_deadline", goals_deadline.strip() or None)
    await crud.set_setting(session, "reflection_deadline", reflection_deadline.strip() or None)
    return RedirectResponse("/dashboard?notice=Сроки+сохранены", status_code=303)


@app.get("/stats", response_class=HTMLResponse)
async def stats(request: Request, session: AsyncSession = Depends(get_session)):
    """Сводка для академического руководителя: кто подтверждён, кто ничего не прислал."""
    if not _is_authed(request):
        return RedirectResponse("/login", status_code=303)
    rows = await crud.director_stats(session)
    goals_deadline = await crud.get_setting(session, "goals_deadline")
    reflection_deadline = await crud.get_setting(session, "reflection_deadline")
    return templates.TemplateResponse(
        request,
        "stats.html",
        {
            "rows": rows,
            "goals_deadline": goals_deadline,
            "reflection_deadline": reflection_deadline,
        },
    )


# --- Коды доступа -----------------------------------------------------------

@app.get("/codes", response_class=HTMLResponse)
async def codes_page(request: Request, session: AsyncSession = Depends(get_session)):
    """Коды доступа: сгенерировать набор, раздать, видеть, кто активировал."""
    if not _is_authed(request):
        return RedirectResponse("/login", status_code=303)
    codes = await crud.list_access_codes(session)
    users = {u.telegram_id: u for u in await crud.list_app_users(session)}
    mentors = await crud.list_mentors(session)
    return templates.TemplateResponse(
        request,
        "codes.html",
        {
            "codes": codes,
            "users": users,
            "mentors": mentors,
            "role_labels": ROLE_LABELS,
            "format_code": crud.format_code,
            "notice": request.query_params.get("notice"),
            "error": request.query_params.get("error"),
        },
    )


@app.post("/codes/generate")
async def codes_generate(
    request: Request,
    students: int = Form(8),
    mentors: int = Form(2),
    directors: int = Form(1),
    session: AsyncSession = Depends(get_session),
):
    if not _is_authed(request):
        return RedirectResponse("/login", status_code=303)
    total = 0
    for role, count, prefix in (
        (ROLE_STUDENT, students, "Студент"),
        (ROLE_MENTOR, mentors, "Наставник"),
        (ROLE_DIRECTOR, directors, "Руководитель"),
    ):
        count = max(0, min(int(count), 100))
        if count:
            total += len(await crud.create_access_codes(session, role, count, prefix))
    return RedirectResponse(f"/codes?notice=Создано+кодов:+{total}", status_code=303)


@app.post("/codes/{code_id}/mentor")
async def code_mentor(
    request: Request,
    code_id: int,
    mentor_tg: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    if not _is_authed(request):
        return RedirectResponse("/login", status_code=303)
    try:
        value = int(mentor_tg) if mentor_tg.strip() else None
    except ValueError:
        return RedirectResponse("/codes?error=Некорректный+наставник", status_code=303)
    await crud.set_access_code_mentor(session, code_id, value)
    return RedirectResponse("/codes?notice=Наставник+закреплён+за+кодом", status_code=303)


@app.post("/codes/{code_id}/release")
async def code_release(request: Request, code_id: int, session: AsyncSession = Depends(get_session)):
    if not _is_authed(request):
        return RedirectResponse("/login", status_code=303)
    await crud.release_access_code(session, code_id)
    return RedirectResponse("/codes?notice=Код+освобождён", status_code=303)


@app.post("/codes/{code_id}/delete")
async def code_delete(request: Request, code_id: int, session: AsyncSession = Depends(get_session)):
    if not _is_authed(request):
        return RedirectResponse("/login", status_code=303)
    await crud.delete_access_code(session, code_id)
    return RedirectResponse("/codes?notice=Код+удалён", status_code=303)
