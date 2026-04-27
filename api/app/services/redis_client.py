"""
Redis client singleton for the tile cache L2 layer.

Redis acts as a shared, persistent cache that survives process
restarts and is shared across multiple Uvicorn workers (when
--workers > 1 is configured). The in-memory L1 LRUCache remains
the primary cache for maximum speed; Redis is only consulted on
L1 misses.
"""
import logging

import redis

from ..config import settings

logger = logging.getLogger(__name__)

_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis | None:
    """
    Returns the Redis client, or None if Redis is disabled
    or unavailable. Callers must handle None gracefully —
    Redis being down must never break tile serving.
    """
    global _redis_client
    if not settings.redis_enabled:
        return None
    if _redis_client is None:
        try:
            _redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                socket_connect_timeout=1,
                socket_timeout=1,
                decode_responses=False,  # tiles are raw bytes
            )
            _redis_client.ping()
        except Exception as e:
            logger.warning("Redis connection failed: %s", e)
            _redis_client = None
    return _redis_client


def close_redis() -> None:
    global _redis_client
    if _redis_client:
        _redis_client.close()
        _redis_client = None
