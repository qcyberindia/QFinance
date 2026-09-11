"""Alembic environment. Imports Base + all module models so autogenerate can see
them. WRITTEN, NOT EXECUTED — `alembic upgrade head` has not run in this session."""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool

from app.core.config import get_settings
from app.core.db import Base

# Import every module's models so Base.metadata is fully populated.
from app.modules.auth import models as _auth_models  # noqa
from app.modules.users import models as _users_models  # noqa
from app.modules.audit import models as _audit_models  # noqa
from app.modules.analytics import models as _analytics_models  # noqa
from app.modules.companies import models as _companies_models  # noqa
from app.modules.research import models as _research_models  # noqa
from app.modules.membership import models as _membership_models  # noqa
from app.modules.billing import models as _billing_models  # noqa
from app.modules.community import models as _community_models  # noqa
from app.modules.moderation import models as _moderation_models  # noqa
from app.modules.journal import models as _journal_models  # noqa
from app.modules.portfolio import models as _portfolio_models  # noqa

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


def run_migrations_offline() -> None:
    context.configure(url=settings.DATABASE_URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(config.get_section(config.config_ini_section), poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
