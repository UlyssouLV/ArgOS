"""Alembic : URL de la base lue dans ARGOS_URL_BASE, comme l'API."""

import logging.config
import os

from alembic import context
from sqlalchemy import create_engine

from argos_api.modeles import Base

if context.config.config_file_name is not None:
    logging.config.fileConfig(context.config.config_file_name)

with create_engine(os.environ["ARGOS_URL_BASE"]).connect() as connexion:
    context.configure(connection=connexion, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
