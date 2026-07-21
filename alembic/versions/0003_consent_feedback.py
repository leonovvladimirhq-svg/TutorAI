"""consent_record (аудит согласий 152-ФЗ) + feedback (обратная связь)

Revision ID: 0003_consent_feedback
Revises: 0002_appuser_roles
Create Date: 2026-07-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_consent_feedback"
down_revision: Union[str, None] = "0002_appuser_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "consent_record",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("doc_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consent_record_telegram_id", "consent_record", ["telegram_id"])

    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("context", sa.String(length=32), nullable=False, server_default="menu"),
        sa.Column("rating", sa.String(length=8), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("ref_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedback_student_id", "feedback", ["student_id"])
    op.create_index("ix_feedback_telegram_id", "feedback", ["telegram_id"])


def downgrade() -> None:
    op.drop_index("ix_feedback_telegram_id", table_name="feedback")
    op.drop_index("ix_feedback_student_id", table_name="feedback")
    op.drop_table("feedback")
    op.drop_index("ix_consent_record_telegram_id", table_name="consent_record")
    op.drop_table("consent_record")
