"""ONVIF en HTTPS : schéma du contact retenu et Certificat de l'Appareil de chaque Caméra.

Revision ID: 0007
Revises: 0006
"""

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cameras", sa.Column("schema_onvif", sa.String(5), nullable=True))
    op.add_column("cameras", sa.Column("empreinte_onvif", sa.String(64), nullable=True))
    op.add_column("cameras", sa.Column("empreinte_onvif_le", sa.DateTime(timezone=True), nullable=True))
    # Les ports déjà retenus l'ont tous été en HTTP ; HTTPS est de toute façon sondé d'abord.
    op.execute("UPDATE cameras SET schema_onvif = 'http' WHERE port_onvif IS NOT NULL")


def downgrade() -> None:
    op.drop_column("cameras", "empreinte_onvif_le")
    op.drop_column("cameras", "empreinte_onvif")
    op.drop_column("cameras", "schema_onvif")
