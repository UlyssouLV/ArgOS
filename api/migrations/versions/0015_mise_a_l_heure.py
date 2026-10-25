"""Mise à l'heure des Caméras : dérive mesurée avant, états `calee` et `recalee` lus « à l'heure ».

Revision ID: 0015
Revises: 0014
"""

from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cameras", sa.Column("horloge_derive_s", sa.Float(), nullable=True))
    op.execute("UPDATE cameras SET horloge_etat = 'a_l_heure' WHERE horloge_etat IN ('calee', 'recalee')")


def downgrade() -> None:
    op.execute("UPDATE cameras SET horloge_etat = 'calee' WHERE horloge_etat = 'a_l_heure'")
    op.drop_column("cameras", "horloge_derive_s")
