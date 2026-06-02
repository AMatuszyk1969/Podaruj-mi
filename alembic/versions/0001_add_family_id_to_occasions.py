"""add family_id to occasions

Revision ID: 0001
Revises:
Create Date: 2026-06-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    # Jeśli tabela nie istnieje, create_all ją stworzy z kolumną – pomijamy
    if "occasions" not in insp.get_table_names():
        return
    existing_cols = [c["name"] for c in insp.get_columns("occasions")]
    if "family_id" not in existing_cols:
        op.add_column(
            "occasions",
            sa.Column("family_id", sa.String(36), nullable=True),
        )
        op.create_foreign_key(
            "fk_occasions_family_id",
            "occasions", "families",
            ["family_id"], ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    if "occasions" not in insp.get_table_names():
        return
    existing_cols = [c["name"] for c in insp.get_columns("occasions")]
    if "family_id" in existing_cols:
        op.drop_constraint("fk_occasions_family_id", "occasions", type_="foreignkey")
        op.drop_column("occasions", "family_id")
