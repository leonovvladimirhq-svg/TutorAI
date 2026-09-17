"""ORM-модели TutorAI.

Ядро — структурированный профиль (profile_attribute) с провенансом (source_ref) и
статусом подтверждения. Точки расширения (memory_chunk, recommendation, nudge, mentor,
cohort) пока не наполняются — добавятся в следующих итерациях.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Student(Base):
    __tablename__ = "student"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, index=True, nullable=True
    )
    profile_label: Mapped[str] = mapped_column(String(64))
    # Пароль больше не используется (вход — по роли из app_user); nullable для
    # обратной совместимости со старыми записями.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # {block_key: "done" | "in_progress"} — какие блоки профиля проработаны
    profiling_progress: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    # Когда студенту отправлено напоминание о рефлексии (по сроку из app_setting); шлём один раз.
    reflection_reminded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    attributes: Mapped[list["ProfileAttribute"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    goals: Mapped[list["Goal"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )


class AppUser(Base):
    """Реестр ролей: Telegram ID → роль. Управляется академ. руководителем в веб-панели.

    role ∈ {"student", "mentor", "director"} (см. app.services.roles).
    """
    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    role: Mapped[str] = mapped_column(String(32))
    full_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Для студентов: telegram_id (MAX-ID) закреплённого наставника. Назначается
    # руководителем в веб-панели; по нему наставник видит «своих» студентов.
    mentor_tg: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_message"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))        # user | assistant | system
    content: Mapped[str] = mapped_column(Text)
    modality: Mapped[str] = mapped_column(String(16), default="text")  # text | voice
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    student: Mapped["Student"] = relationship(back_populates="messages")


class ProfileAttribute(Base):
    __tablename__ = "profile_attribute"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    block: Mapped[str] = mapped_column(String(64))       # ключ блока (profile_schema)
    key: Mapped[str] = mapped_column(String(128))        # атрибут внутри блока
    value: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source_ref: Mapped[int | None] = mapped_column(
        ForeignKey("conversation_message.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="suggested")  # suggested|confirmed|edited
    visible_to_mentor: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    student: Mapped["Student"] = relationship(back_populates="attributes")


class Goal(Base):
    __tablename__ = "goal"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    # компоненты SMART
    specific: Mapped[str | None] = mapped_column(Text, nullable=True)
    measurable: Mapped[str | None] = mapped_column(Text, nullable=True)
    achievable: Mapped[str | None] = mapped_column(Text, nullable=True)
    relevant: Mapped[str | None] = mapped_column(Text, nullable=True)
    time_bound: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft|active|done|dropped
    progress: Mapped[int] = mapped_column(Integer, default=0)         # 0..100
    source_ref: Mapped[int | None] = mapped_column(
        ForeignKey("conversation_message.id", ondelete="SET NULL"), nullable=True
    )
    # Контур подтверждения наставником: pending → confirmed | rejected.
    # При отклонении наставник пишет причину — она уходит студенту и хранится здесь.
    confirm_status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending"
    )
    mentor_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Актуализация: если цель перестала быть актуальной, студент отмечает это
    # (status → dropped) и поясняет почему.
    relevance_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    student: Mapped["Student"] = relationship(back_populates="goals")
    reflections: Mapped[list["GoalReflection"]] = relationship(
        back_populates="goal", cascade="all, delete-orphan"
    )

    def is_complete(self) -> bool:
        """Все 5 компонентов SMART заполнены."""
        return all([self.specific, self.measurable, self.achievable, self.relevant, self.time_bound])


class EventLog(Base):
    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("student.id", ondelete="SET NULL"), index=True, nullable=True
    )
    type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ConsentRecord(Base):
    """Аудит-след согласий на обработку ПДн (152-ФЗ).

    Одна запись — один акт согласия/отказа/отзыва по конкретной версии документа.
    Ключ — telegram_id (работает для любой роли, не только студента). Актуальность
    согласия определяется последней записью со статусом ``accepted`` для текущей
    версии документа (см. app.services.consent).
    """
    __tablename__ = "consent_record"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    doc_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))  # accepted | declined | revoked
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Feedback(Base):
    """Обратная связь студента: 👍/👎 + необязательный комментарий.

    context — где оставлена (``menu`` | ``smart_goal`` | …); ref_id — id связанного
    объекта (например, goal.id) при контекстной обратной связи.
    """
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("student.id", ondelete="SET NULL"), index=True, nullable=True
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    context: Mapped[str] = mapped_column(String(32), default="menu")
    rating: Mapped[str] = mapped_column(String(8))  # up | down
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ReflectionSession(Base):
    """Одно подведение итогов по целям (рефлексия) за период.

    Порядок по требованию заказчика: сначала студент САМ формулирует
    закономерности (student_patterns), и только потом ИИ даёт сводку (ai_summary).
    completed_at пуст, пока сессия не завершена.
    """
    __tablename__ = "reflection_session"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    student_patterns: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    goal_reflections: Mapped[list["GoalReflection"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class GoalReflection(Base):
    """Рефлексия студента по одной цели внутри сессии.

    outcome — achieved | partial | not_achieved | irrelevant.
    answers — {ключ вопроса: ответ}: what_done, why, thanks_to, differently,
    self_assess, mentor_assess, praise. Степень достижения НЕ оценивается —
    предмет оценки наставника только глубина рефлексии.
    """
    __tablename__ = "goal_reflection"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("reflection_session.id", ondelete="CASCADE"), index=True
    )
    goal_id: Mapped[int] = mapped_column(ForeignKey("goal.id", ondelete="CASCADE"), index=True)
    outcome: Mapped[str] = mapped_column(String(16))
    answers: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped["ReflectionSession"] = relationship(back_populates="goal_reflections")
    goal: Mapped["Goal"] = relationship(back_populates="reflections")


class AppSetting(Base):
    """Настройки периода, задаваемые руководителем в веб-панели (key → value).

    Ключи: goals_deadline, reflection_deadline (даты YYYY-MM-DD).
    """
    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AccessCode(Base):
    """Код доступа (16 цифр) — вход в систему без ручного назначения по MAX-ID.

    Руководитель генерирует набор кодов в веб-панели и раздаёт их: студент вводит код
    в боте и получает роль, записанную в коде. У студенческого кода может быть заранее
    закреплён наставник — тогда привязка сохраняется даже после /forget_me
    (код освобождается и его можно ввести заново).
    """
    __tablename__ = "access_code"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(32))
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mentor_tg: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    used_by_tg: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
