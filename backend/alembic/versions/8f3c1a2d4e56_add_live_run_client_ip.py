"""add live-run client IP hash and date indexes

Revision ID: 8f3c1a2d4e56
Revises: dc9f5e2710fd
Create Date: 2026-10-28 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8f3c1a2d4e56"
down_revision: str | None = "dc9f5e2710fd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("client_ip_hash", sa.String(length=64), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_runs_client_ip_hash"), ["client_ip_hash"], unique=False
        )
        batch_op.create_index("ix_runs_client_ip_hash_created_at", ["client_ip_hash", "created_at"])
        batch_op.create_index("ix_runs_created_at", ["created_at"])


def downgrade() -> None:
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_index("ix_runs_created_at")
        batch_op.drop_index("ix_runs_client_ip_hash_created_at")
        batch_op.drop_index(batch_op.f("ix_runs_client_ip_hash"))
        batch_op.drop_column("client_ip_hash")
