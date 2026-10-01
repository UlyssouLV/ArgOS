"""Caméras du Site.

Revision ID: 0003
Revises: 0002
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cameras",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nom", sa.String, nullable=False, unique=True),
        sa.Column("url_rtsp", sa.String, nullable=False, unique=True),
        sa.Column("emplacement", sa.String, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("etat", sa.String(16), nullable=False),
        sa.Column("etat_verifie_le", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("cameras")
