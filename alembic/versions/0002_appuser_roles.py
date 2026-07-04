"""app_user (роли по Telegram ID) + student.password_hash nullable

Revision ID: 0002_appuser_roles
Revises: 0001_initial
Create Date: 2026-07-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_appuser_roles"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("full_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_app_user_telegram_id", "app_user", ["telegram_id"], unique=True)

    # Пароль больше не используется — вход по роли из app_user.
    op.alter_column("student", "password_hash", existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    op.alter_column("student", "password_hash", existing_type=sa.String(length=255), nullable=False)
    op.drop_index("ix_app_user_telegram_id", table_name="app_user")
    op.drop_table("app_user")
