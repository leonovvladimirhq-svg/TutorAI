"""Отчёт для наставника по студенту — .docx из реальных данных.

Структура по согласованному макету: шапка, сводка целей, разбор по каждой цели
(SMART + решение наставника + рефлексия), закономерности (сначала слова студента,
потом сводка ИИ), критерии оценивания для наставника. Степень достижения целей
не оценивается — предмет оценки только качество целей и глубина рефлексии.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import crud
from app.services.reflection import OUTCOME_LABELS, QUESTION_LABELS

ACCENT = RGBColor(0x5B, 0x4B, 0x9E)
GREY = RGBColor(0x77, 0x77, 0x77)
OK = RGBColor(0x1E, 0x84, 0x49)
MID = RGBColor(0xB7, 0x79, 0x1F)
BAD = RGBColor(0xC0, 0x39, 0x2B)

_STATUS_RU = {"draft": "черновик", "active": "активна", "done": "достигнута", "dropped": "снята"}
_CONFIRM_RU = {"pending": ("ждёт подтверждения", MID), "confirmed": ("подтверждена", OK), "rejected": ("возвращена на доработку", BAD)}
_OUTCOME_COLOR = {"achieved": OK, "partial": MID, "not_achieved": BAD, "irrelevant": GREY}

CRITERIA = [
    "Цели полноценные, ясные по SMART, чёткие и понятные.",
    "Есть ясный план выполнения — что конкретно студент будет делать.",
    "В отчёте есть отметки о движении по всем целям и действиям.",
    "Рефлексия глубокая и полноценная: видно, что студент задумывался о происходящем.",
    "Степень достижения цели НЕ оценивается: студент может не достичь ничего, но качественно отрефлексировать результат.",
]


def _shade(cell, hex_fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tc_pr.append(shd)


def _run(p, text: str, bold=False, italic=False, color: RGBColor | None = None, size: int | None = None):
    r = p.add_run(text)
    r.bold = bold
    r.italic = italic
    if color is not None:
        r.font.color.rgb = color
    if size is not None:
        r.font.size = Pt(size)
    return r


def _para(doc, text: str = "", **kw):
    p = doc.add_paragraph()
    if text:
        _run(p, text, **kw)
    p.paragraph_format.space_after = Pt(6)
    return p


def _kv_table(doc, rows: list[tuple[str, str]], key_fill="F4F2FA", key_w=5.0, val_w=12.0):
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    for k, v in rows:
        cells = t.add_row().cells
        cells[0].width, cells[1].width = Cm(key_w), Cm(val_w)
        _shade(cells[0], key_fill)
        _run(cells[0].paragraphs[0], k, bold=True, color=GREY, size=9.5)
        _run(cells[1].paragraphs[0], v or "—", size=9.5)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)
    return t


def _fmt_dt(dt: datetime | None) -> str:
    return dt.strftime("%d.%m.%Y") if dt else "—"


async def build_student_report(session: AsyncSession, app_user) -> tuple[bytes, str]:
    """Собрать .docx по студенту (запись реестра ролей). Возвращает (bytes, имя файла)."""
    student = await crud.get_student_by_tg(session, app_user.telegram_id)
    goals = await crud.list_goals(session, student.id) if student else []
    refl = await crud.latest_completed_reflection(session, student.id) if student else None
    grefl = {}
    if refl:
        for gr in await crud.list_goal_reflections(session, refl.id):
            grefl[gr.goal_id] = gr
    mentor = await crud.get_app_user_by_tg(session, app_user.mentor_tg) if app_user.mentor_tg else None
    goals_deadline = await crud.get_setting(session, "goals_deadline")
    reflection_deadline = await crud.get_setting(session, "reflection_deadline")

    name = app_user.full_name or f"ID {app_user.telegram_id}"
    doc = Document()
    for s in doc.sections:
        s.left_margin = s.right_margin = Cm(2)
        s.top_margin = s.bottom_margin = Cm(2)
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(10.5)

    # --- шапка ---
    p = doc.add_paragraph()
    _run(p, "Индивидуальная карта целей студента", bold=True, color=ACCENT, size=18)
    p = doc.add_paragraph()
    _run(p, "TutorAI · ИИ-наставник · Школа коммуникаций НИУ ВШЭ", color=GREY, size=10)
    p.paragraph_format.space_after = Pt(10)

    _kv_table(doc, [
        ("Студент", name),
        ("ID в MAX", str(app_user.telegram_id)),
        ("Наставник", (mentor.full_name or str(mentor.telegram_id)) if mentor else "не назначен"),
        ("Срок подачи целей", goals_deadline or "не задан"),
        ("Срок рефлексии", reflection_deadline or "не задан"),
        ("Целей поставлено", str(len(goals))),
        ("Рефлексия пройдена", _fmt_dt(refl.completed_at) if refl else "ещё нет"),
        ("Отчёт сформирован", datetime.now().strftime("%d.%m.%Y %H:%M")),
    ])

    _para(doc, "Что это за документ", bold=True, color=ACCENT, size=12)
    _para(doc, "Это не ведомость успеваемости: здесь не выставляются оценки и не фиксируются "
               "нарушения. Документ отражает то, что студент поставил себе сам, что из этого "
               "получилось, как он это осмыслил — и какие закономерности за этим видны. "
               "Он передаётся наставнику как основа для разговора, а не как отчёт о проделанной работе.")
    _para(doc, "Степень достижения целей не оценивается. Предмет оценки — качество целей и глубина рефлексии.",
          italic=True, color=GREY, size=9.5)

    # --- 1. сводка ---
    doc.add_heading("1. Цели периода: сводка", level=1)
    if not goals:
        _para(doc, "Студент пока не поставил ни одной цели.", italic=True, color=GREY)
    else:
        t = doc.add_table(rows=1, cols=4)
        t.style = "Table Grid"
        for i, h in enumerate(["№", "Цель", "Решение наставника", "Итог рефлексии"]):
            c = t.rows[0].cells[i]
            _shade(c, "5B4B9E")
            _run(c.paragraphs[0], h, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), size=9.5)
        for n, g in enumerate(goals, 1):
            cells = t.add_row().cells
            _run(cells[0].paragraphs[0], str(n), size=9.5)
            _run(cells[1].paragraphs[0], g.title, size=9.5)
            label, color = _CONFIRM_RU.get(g.confirm_status, (g.confirm_status, GREY))
            _run(cells[2].paragraphs[0], label, bold=True, color=color, size=9.5)
            gr = grefl.get(g.id)
            if g.status == "dropped":
                _run(cells[3].paragraphs[0], OUTCOME_LABELS["irrelevant"], bold=True, color=GREY, size=9.5)
            elif gr:
                _run(cells[3].paragraphs[0], OUTCOME_LABELS.get(gr.outcome, gr.outcome), bold=True,
                     color=_OUTCOME_COLOR.get(gr.outcome, GREY), size=9.5)
            else:
                _run(cells[3].paragraphs[0], "рефлексии ещё нет", color=GREY, size=9.5)
        doc.add_paragraph().paragraph_format.space_after = Pt(4)

    # --- 2. разбор по целям ---
    doc.add_heading("2. Разбор по каждой цели", level=1)
    for n, g in enumerate(goals, 1):
        p = doc.add_paragraph()
        _run(p, f"Цель {n}. {g.title}", bold=True, color=ACCENT, size=12)
        p.paragraph_format.space_before = Pt(10)
        _kv_table(doc, [
            ("S — конкретность", g.specific or "—"),
            ("M — измеримость", g.measurable or "—"),
            ("A — достижимость", g.achievable or "—"),
            ("R — значимость", g.relevant or "—"),
            ("T — срок", g.time_bound or "—"),
        ], key_fill="F7F6FC")
        label, color = _CONFIRM_RU.get(g.confirm_status, (g.confirm_status, GREY))
        p = doc.add_paragraph()
        _run(p, "Решение наставника: ", bold=True)
        _run(p, label, bold=True, color=color)
        if g.mentor_comment:
            _run(p, f" — «{g.mentor_comment}»", italic=True)
        if g.status == "dropped":
            p = doc.add_paragraph()
            _run(p, "Актуальность: ", bold=True)
            _run(p, "студент отметил, что цель потеряла актуальность", color=GREY)
            if g.relevance_note:
                _run(p, f" — «{g.relevance_note}»", italic=True)
        gr = grefl.get(g.id)
        if gr:
            p = doc.add_paragraph()
            _run(p, "Итог по словам студента: ", bold=True)
            _run(p, OUTCOME_LABELS.get(gr.outcome, gr.outcome), bold=True, color=_OUTCOME_COLOR.get(gr.outcome, GREY))
            for key, qlabel in QUESTION_LABELS.items():
                ans = (gr.answers or {}).get(key)
                if ans:
                    p = doc.add_paragraph()
                    _run(p, f"{qlabel}: ", bold=True, color=ACCENT, size=10)
                    _run(p, f"«{ans}»", italic=True, size=10)
        elif g.status != "dropped":
            _para(doc, "Рефлексия по этой цели ещё не проводилась.", italic=True, color=GREY, size=9.5)

    # --- 3. закономерности ---
    doc.add_heading("3. Закономерности: взгляд студента и сводка системы", level=1)
    if refl and (refl.student_patterns or refl.ai_summary):
        _para(doc, "Что студент увидел сам", bold=True, color=ACCENT, size=11)
        _para(doc, f"«{refl.student_patterns}»" if refl.student_patterns else "Студент не сформулировал закономерности.",
              italic=bool(refl.student_patterns), color=None if refl.student_patterns else GREY)
        _para(doc, "Что добавила система", bold=True, color=ACCENT, size=11)
        _para(doc, refl.ai_summary or "Сводка не сформирована.", color=None if refl.ai_summary else GREY)
    else:
        _para(doc, "Раздел заполнится после того, как студент пройдёт подведение итогов по целям.",
              italic=True, color=GREY)

    # --- 4. критерии ---
    doc.add_heading("4. Критерии оценивания (для наставника)", level=1)
    _para(doc, "Те же критерии, что применяются к письменному заданию. Отметьте, что видите в материале выше:")
    for c in CRITERIA:
        p = doc.add_paragraph(style="List Bullet")
        _run(p, "☐  " + c, size=10)
    _para(doc, "К разговору с наставником: обсуждать не «почему не сделал», а что именно происходило "
               "на каждом шаге и что студент об этом думает.", italic=True, color=GREY, size=9.5)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    _run(p, "Сформировано автоматически системой TutorAI. Данные обрабатываются в соответствии "
            "с согласием студента (152-ФЗ).", italic=True, color=GREY, size=8.5)

    buf = BytesIO()
    doc.save(buf)
    safe = "".join(ch for ch in name if ch.isalnum() or ch in " _-").strip().replace(" ", "_") or "student"
    return buf.getvalue(), f"TutorAI_отчёт_{safe}.docx"
