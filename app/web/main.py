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
from app.services.roles import ROLE_LABELS, ROLES, is_valid_role

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
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "users": users,
            "roles": ROLES,
            "role_labels": ROLE_LABELS,
            "notice": request.query_params.get("notice"),
            "error": request.query_params.get("error"),
        },
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
