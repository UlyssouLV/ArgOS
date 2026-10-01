"""Sessions durcies : empreinte du mot de passe en vigueur à l'ouverture.

Revision ID: 0002
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Les sessions ouvertes avant n'ont pas d'empreinte : elles seraient refusées de toute façon.
    op.execute("DELETE FROM sessions")
    op.add_column("sessions", sa.Column("empreinte_mot_de_passe", sa.String(64), nullable=False))
    # L'heure d'ouverture vient de l'horloge de l'application, plus de la base.
    op.alter_column("sessions", "cree_le", server_default=None)


def downgrade() -> None:
    op.alter_column("sessions", "cree_le", server_default=sa.func.now())
    op.drop_column("sessions", "empreinte_mot_de_passe")
