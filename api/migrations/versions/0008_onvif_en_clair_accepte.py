"""ONVIF en clair : accord de l'Administrateur pour chaque Caméra sans HTTPS.

Revision ID: 0008
Revises: 0007
"""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aucun accord au départ : une Caméra déjà réglée en HTTP le demande à l'ouverture de ses Réglages.
    op.add_column(
        "cameras",
        sa.Column("onvif_en_clair_accepte", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("cameras", "onvif_en_clair_accepte")
