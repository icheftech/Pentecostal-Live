"""stream ingest key for media relay

Revision ID: 0004_stream_ingest
Revises: 0003_refresh_tokens
Create Date: 2026-07-08 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_stream_ingest"
down_revision: Union[str, None] = "0003_refresh_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("streams", sa.Column("ingest_key", sa.String(64), nullable=True))
    op.create_index("ix_streams_ingest_key", "streams", ["ingest_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_streams_ingest_key", table_name="streams")
    op.drop_column("streams", "ingest_key")
