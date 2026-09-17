"""коды доступа: регистрация по 16-значному коду вместо ручного назначения по MAX-ID

Revision ID: 0005_access_codes
Revises: 0004_mentor_reflection
Create Date: 2026-09-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_access_codes"
down_revision: Union[str, None] = "0004_mentor_reflection"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "access_code",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column("mentor_tg", sa.BigInteger(), nullable=True),
        sa.Column("used_by_tg", sa.BigInteger(), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_access_code_code"),
    )
    op.create_index("ix_access_code_code", "access_code", ["code"])
    op.create_index("ix_access_code_used_by_tg", "access_code", ["used_by_tg"])


def downgrade() -> None:
    op.drop_index("ix_access_code_used_by_tg", table_name="access_code")
    op.drop_index("ix_access_code_code", table_name="access_code")
    op.drop_table("access_code")
