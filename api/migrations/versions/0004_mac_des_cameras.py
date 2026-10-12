"""MAC de l'Appareil de chaque Caméra et raison de son état.

Revision ID: 0004
Revises: 0003
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Non unique : un Appareil peut porter plusieurs Caméras. Inconnue pour les Caméras d'avant la 0.4.2.
    op.add_column("cameras", sa.Column("mac", sa.String(17), nullable=True))
    op.add_column("cameras", sa.Column("raison_etat", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("cameras", "raison_etat")
    op.drop_column("cameras", "mac")
