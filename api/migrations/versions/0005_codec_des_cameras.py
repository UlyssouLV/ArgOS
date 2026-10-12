"""Codec de chaque Caméra.

Revision ID: 0005
Revises: 0004
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sans longueur : le SDP d'une caméra peut nommer n'importe quel encodage. Inconnu pour les Caméras
    # d'avant la 0.5.0 : la sonde le remplit à son passage suivant.
    op.add_column("cameras", sa.Column("codec", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("cameras", "codec")
