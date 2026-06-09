"""add summary_sent to occasions

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    if "occasions" not in insp.get_table_names():
        return
    cols = [c["name"] for c in insp.get_columns("occasions")]
    if "summary_sent" not in cols:
        op.add_column(
            "occasions",
            sa.Column("summary_sent", sa.Boolean(), nullable=False,
                      server_default=sa.false()),
        )
        # Backfill: już zakończone okazje oznaczamy jako podsumowane,
        # żeby po wdrożeniu nie wysyłać zaległych maili podsumowujących.
        op.execute("UPDATE occasions SET summary_sent = true "
                   "WHERE pledge_deadline < CURRENT_TIMESTAMP")


def downgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)
    if "occasions" not in insp.get_table_names():
        return
    cols = [c["name"] for c in insp.get_columns("occasions")]
    if "summary_sent" in cols:
        op.drop_column("occasions", "summary_sent")
