"""модуль наставника: привязка наставника, подтверждение целей, рефлексия, сроки

Revision ID: 0004_mentor_reflection
Revises: 0003_consent_feedback
Create Date: 2026-09-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_mentor_reflection"
down_revision: Union[str, None] = "0003_consent_feedback"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Привязка студент → наставник (в реестре ролей, чтобы работала до согласия).
    op.add_column("app_user", sa.Column("mentor_tg", sa.BigInteger(), nullable=True))
    op.create_index("ix_app_user_mentor_tg", "app_user", ["mentor_tg"])

    # Напоминание о рефлексии — отправляется один раз по сроку.
    op.add_column(
        "student",
        sa.Column("reflection_reminded_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Контур подтверждения наставником + актуализация цели.
    op.add_column(
        "goal",
        sa.Column("confirm_status", sa.String(length=16), nullable=False, server_default="pending"),
    )
    op.add_column("goal", sa.Column("mentor_comment", sa.Text(), nullable=True))
    op.add_column("goal", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("goal", sa.Column("relevance_note", sa.Text(), nullable=True))

    # Рефлексия: сессия (закономерности студента → сводка ИИ) и ответы по целям.
    op.create_table(
        "reflection_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("student_patterns", sa.Text(), nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reflection_session_student_id", "reflection_session", ["student_id"])

    op.create_table(
        "goal_reflection",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("goal_id", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["reflection_session.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["goal_id"], ["goal.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_goal_reflection_session_id", "goal_reflection", ["session_id"])
    op.create_index("ix_goal_reflection_goal_id", "goal_reflection", ["goal_id"])

    # Настройки периода (сроки), задаваемые руководителем в веб-панели.
    op.create_table(
        "app_setting",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("app_setting")
    op.drop_index("ix_goal_reflection_goal_id", table_name="goal_reflection")
    op.drop_index("ix_goal_reflection_session_id", table_name="goal_reflection")
    op.drop_table("goal_reflection")
    op.drop_index("ix_reflection_session_student_id", table_name="reflection_session")
    op.drop_table("reflection_session")
    op.drop_column("goal", "relevance_note")
    op.drop_column("goal", "confirmed_at")
    op.drop_column("goal", "mentor_comment")
    op.drop_column("goal", "confirm_status")
    op.drop_column("student", "reflection_reminded_at")
    op.drop_index("ix_app_user_mentor_tg", table_name="app_user")
    op.drop_column("app_user", "mentor_tg")
