"""Port ONVIF de chaque Caméra.

Revision ID: 0006
Revises: 0005
"""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Inconnu tant que les Réglages de la Caméra n'ont pas été ouverts : ArgOS le cherche alors lui-même.
    op.add_column("cameras", sa.Column("port_onvif", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("cameras", "port_onvif")
