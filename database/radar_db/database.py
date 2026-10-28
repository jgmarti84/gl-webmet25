# database/radar_db/database.py
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
from typing import Generator
import logging
from alembic.config import Config
from alembic import command

from radar_db.config import settings
from radar_db.models import Base

logger = logging.getLogger(__name__)


def _is_versioned(engine) -> bool:
    """True when the database already has an Alembic version row."""
    if "alembic_version" not in inspect(engine).get_table_names():
        return False
    with engine.connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM alembic_version")).scalar() > 0


def sync_alembic_version(engine, alembic_cfg) -> str:
    """Bring Alembic in line with the schema create_all just built.

    * A database that already has a version row: apply the pending migrations (create_all never adds
      columns to existing tables). A failure propagates: stamping over it would hide a half-applied schema.
    * A database without a version (fresh, or created before Alembic): stamp it at head.

    Returns "upgraded" or "stamped".
    """
    if _is_versioned(engine):
        command.upgrade(alembic_cfg, "head")
        return "upgraded"
    command.stamp(alembic_cfg, "head")
    return "stamped"


class DatabaseManager:
    """Manages database connections and sessions."""
    
    _instance = None
    _engine = None
    _SessionLocal = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._engine is None:
            self._initialize_engine()
    
    def _initialize_engine(self):
        self._engine = create_engine(
            settings.database_url,
            poolclass=QueuePool,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
            pool_recycle=300,
            echo=False,
        )
        
        self._SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self._engine
        )
        
        logger.info(f"Database engine initialized: {settings.db_host}:{settings.db_port}/{settings.db_name}")
    
    @property
    def engine(self):
        return self._engine
    
    @property
    def SessionLocal(self):
        return self._SessionLocal
    
    def create_all_tables(self):
        with self._engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            conn.commit()
        Base.metadata.create_all(bind=self._engine)
        logger.info("All database tables created")
        
        # Apply pending migrations on an existing database; only a database without a version is stamped.
        outcome = sync_alembic_version(self._engine, Config("alembic.ini"))
        logger.info("Alembic %s to head", outcome)

    def drop_all_tables(self):
        Base.metadata.drop_all(bind=self._engine)
        logger.warning("All database tables dropped")
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        session = self._SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def get_session_direct(self) -> Session:
        return self._SessionLocal()


db_manager = DatabaseManager()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency."""
    session = db_manager.get_session_direct()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    db_manager.create_all_tables()


def check_db_connection() -> bool:
    try:
        with db_manager.get_session() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False