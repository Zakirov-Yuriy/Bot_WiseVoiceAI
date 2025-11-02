"""
Redis caching layer for the bot application.
Provides caching for transcription results and user data.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Union
import hashlib
import redis.asyncio as redis
from .config import REDIS_URL, REDIS_CACHE_TTL, REDIS_USER_CACHE_TTL

logger = logging.getLogger(__name__)


class CacheManager:
    """Redis cache manager for transcription results and user data"""

    def __init__(self, redis_url: str = REDIS_URL):
        self.redis_url = redis_url
        self._redis: Optional[redis.Redis] = None

    async def get_redis(self) -> redis.Redis:
        """Get Redis connection with lazy initialization"""
        if self._redis is None:
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def close(self):
        """Close Redis connection"""
        if self._redis:
            await self._redis.close()
            self._redis = None

    def _generate_file_hash(self, file_path: str, user_id: int) -> str:
        """Generate hash for file-based caching"""
        with open(file_path, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        return f"transcription:{user_id}:{file_hash}"

    def _generate_user_cache_key(self, user_id: int, key: str) -> str:
        """Generate cache key for user data"""
        return f"user:{user_id}:{key}"

    async def get_transcription_result(self, file_path: str, user_id: int) -> Optional[List[Dict[str, str]]]:
        """Get cached transcription result"""
        try:
            redis_client = await self.get_redis()
            cache_key = self._generate_file_hash(file_path, user_id)
            cached_data = await redis_client.get(cache_key)

            if cached_data:
                logger.info(f"Cache hit for transcription: {cache_key}")
                return json.loads(cached_data)
            else:
                logger.info(f"Cache miss for transcription: {cache_key}")
                return None
        except Exception as e:
            logger.warning(f"Error retrieving transcription cache: {e}")
            return None

    async def set_transcription_result(self, file_path: str, user_id: int, segments: List[Dict[str, str]]) -> bool:
        """Cache transcription result"""
        try:
            redis_client = await self.get_redis()
            cache_key = self._generate_file_hash(file_path, user_id)
            data = json.dumps(segments, ensure_ascii=False)

            success = await redis_client.setex(cache_key, REDIS_CACHE_TTL, data)
            if success:
                logger.info(f"Cached transcription result: {cache_key}")
            return bool(success)
        except Exception as e:
            logger.warning(f"Error caching transcription result: {e}")
            return False

    async def get_user_data(self, user_id: int, key: str) -> Optional[Any]:
        """Get cached user data"""
        try:
            redis_client = await self.get_redis()
            cache_key = self._generate_user_cache_key(user_id, key)
            cached_data = await redis_client.get(cache_key)

            if cached_data:
                logger.debug(f"Cache hit for user data: {cache_key}")
                return json.loads(cached_data)
            else:
                logger.debug(f"Cache miss for user data: {cache_key}")
                return None
        except Exception as e:
            logger.warning(f"Error retrieving user cache: {e}")
            return None

    async def set_user_data(self, user_id: int, key: str, data: Any) -> bool:
        """Cache user data"""
        try:
            redis_client = await self.get_redis()
            cache_key = self._generate_user_cache_key(user_id, key)
            json_data = json.dumps(data, ensure_ascii=False)

            success = await redis_client.setex(cache_key, REDIS_USER_CACHE_TTL, json_data)
            if success:
                logger.debug(f"Cached user data: {cache_key}")
            return bool(success)
        except Exception as e:
            logger.warning(f"Error caching user data: {e}")
            return False

    async def delete_user_data(self, user_id: int, key: str) -> bool:
        """Delete cached user data"""
        try:
            redis_client = await self.get_redis()
            cache_key = self._generate_user_cache_key(user_id, key)
            result = await redis_client.delete(cache_key)
            logger.debug(f"Deleted user cache: {cache_key}")
            return result > 0
        except Exception as e:
            logger.warning(f"Error deleting user cache: {e}")
            return False

    async def invalidate_user_cache(self, user_id: int) -> bool:
        """Invalidate all cached data for a user"""
        try:
            redis_client = await self.get_redis()
            pattern = f"user:{user_id}:*"
            keys = await redis_client.keys(pattern)

            if keys:
                result = await redis_client.delete(*keys)
                logger.info(f"Invalidated {result} cache entries for user {user_id}")
                return result > 0
            return True
        except Exception as e:
            logger.warning(f"Error invalidating user cache: {e}")
            return False

    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            redis_client = await self.get_redis()
            info = await redis_client.info()

            # Count keys by pattern
            transcription_keys = len(await redis_client.keys("transcription:*"))
            user_keys = len(await redis_client.keys("user:*"))

            return {
                "redis_connected": True,
                "used_memory": info.get("used_memory_human", "N/A"),
                "total_connections_received": info.get("total_connections_received", 0),
                "transcription_cache_entries": transcription_keys,
                "user_cache_entries": user_keys,
                "total_cache_entries": transcription_keys + user_keys
            }
        except Exception as e:
            logger.warning(f"Error getting cache stats: {e}")
            return {
                "redis_connected": False,
                "error": str(e)
            }


# Global cache manager instance
cache_manager = CacheManager()


async def init_cache():
    """Initialize cache connection"""
    try:
        redis_client = await cache_manager.get_redis()
        await redis_client.ping()
        logger.info("Redis cache initialized successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize Redis cache: {e}")


async def close_cache():
    """Close cache connection"""
    await cache_manager.close()
