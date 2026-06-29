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
    password_hash: Mapped[str] = mapped_column(String(255))
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # {block_key: "done" | "in_progress"} — какие блоки профиля проработаны
    profiling_progress: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    student: Mapped["Student"] = relationship(back_populates="goals")

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
