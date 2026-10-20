"""Vérification de l'Horloge des Caméras : état, écart mesuré et date de la dernière.

Revision ID: 0014
Revises: 0013
"""

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cameras", sa.Column("horloge_etat", sa.String(16), nullable=True))
    op.add_column("cameras", sa.Column("horloge_ecart_s", sa.Float(), nullable=True))
    op.add_column("cameras", sa.Column("horloge_verifiee_le", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("cameras", "horloge_verifiee_le")
    op.drop_column("cameras", "horloge_ecart_s")
    op.drop_column("cameras", "horloge_etat")
