"""Réglages Site : conservation des Segments d'enregistrement.

Revision ID: 0010
Revises: 0009
"""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reglages_site",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conservation_h", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(sa.text("INSERT INTO reglages_site (id, conservation_h) VALUES (1, 1)"))


def downgrade() -> None:
    op.drop_table("reglages_site")
