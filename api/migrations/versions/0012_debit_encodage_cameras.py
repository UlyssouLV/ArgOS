"""Débit d'encodage connu par Caméra (repli du Débit d'écriture).

Revision ID: 0012
Revises: 0011
"""

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cameras", sa.Column("debit_encodage_kbit_s", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("cameras", "debit_encodage_kbit_s")
