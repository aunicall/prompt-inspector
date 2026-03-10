"""Database connection and session management."""

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings
from app.logger import logger

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=10,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    """Dependency injection for database sessions."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database: auto-create DB, enable pgvector, create tables, build HNSW index."""
    db_url = settings.DATABASE_URL
    url = make_url(db_url)
    target_db = url.database

    logger.info(f"Connecting to database: {url.host}:{url.port} (db: {target_db})")

    # Create target database if not exists
    postgres_url = url.set(database="postgres")
    sys_engine = create_async_engine(postgres_url, isolation_level="AUTOCOMMIT")
    try:
        async with sys_engine.connect() as conn:
            check_db_query = text("SELECT 1 FROM pg_database WHERE datname = :db")
            result = await conn.execute(check_db_query, {"db": target_db})
            if not result.scalar():
                logger.info(f"Database '{target_db}' not found, creating...")
                await conn.execute(text(f'CREATE DATABASE "{target_db}"'))
                logger.info(f"Database '{target_db}' created successfully.")
            else:
                logger.info(f"Database '{target_db}' already exists.")
    except Exception as e:
        logger.warning(f"Warning during database auto-creation: {e}")
    finally:
        await sys_engine.dispose()

    # Enable pgvector extension
    setup_engine = create_async_engine(db_url, isolation_level="AUTOCOMMIT")
    try:
        async with setup_engine.connect() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            logger.info("Extension 'vector' verified.")
    except Exception as e:
        logger.error(f"Failed to create 'vector' extension: {e}")
    finally:
        await setup_engine.dispose()

    # Create all tables
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database schema synchronized.")
    except Exception as e:
        logger.error(f"ORM schema sync failed: {e}")
        raise

    # Create HNSW vector index
    idx_engine = create_async_engine(db_url, isolation_level="AUTOCOMMIT")
    try:
        async with idx_engine.connect() as conn:
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS vector_payloads_embedding_idx "
                "ON vector_payloads USING hnsw (embedding halfvec_cosine_ops) "
                "WITH (m = 16, ef_construction = 128);"
            ))
            logger.info("HNSW vector index verified.")
    except Exception as e:
        logger.warning(f"Warning during HNSW index creation: {e}")
    finally:
        await idx_engine.dispose()
