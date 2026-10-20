"""Heure du Site : source de l'heure et fuseau.

Revision ID: 0013
Revises: 0012
"""

from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reglages_site", sa.Column("heure_source", sa.String(16), nullable=False, server_default="ntp"))
    op.add_column(
        "reglages_site", sa.Column("heure_serveur_ntp", sa.String(), nullable=False, server_default="pool.ntp.org")
    )
    op.add_column("reglages_site", sa.Column("fuseau", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("reglages_site", "fuseau")
    op.drop_column("reglages_site", "heure_serveur_ntp")
    op.drop_column("reglages_site", "heure_source")
