"""Seuil de place disque sur les réglages Site.

Revision ID: 0011
Revises: 0010
"""

from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

SEUIL_DEFAUT = 1_073_741_824  # 1 Go


def upgrade() -> None:
    op.add_column(
        "reglages_site",
        sa.Column(
            "seuil_octets_libres",
            sa.BigInteger(),
            nullable=False,
            server_default=str(SEUIL_DEFAUT),
        ),
    )


def downgrade() -> None:
    op.drop_column("reglages_site", "seuil_octets_libres")
