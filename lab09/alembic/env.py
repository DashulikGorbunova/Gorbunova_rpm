from alembic import context
from sqlalchemy import create_engine, pool
from app.core.config import Settings
from app.models import Base

config = context.config
target_metadata = Base.metadata

def offline():
    context.configure(url=Settings().database_url, target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={'paramstyle':'named'})
    with context.begin_transaction():
        context.run_migrations()

def online():
    engine = create_engine(Settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()

if context.is_offline_mode():
    offline()
else:
    online()
