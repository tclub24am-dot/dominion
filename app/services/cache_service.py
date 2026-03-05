# -*- coding: utf-8 -*-
# app/services/cache_service.py
"""
CacheService - Redis- caching service for S-GLOBAL Dominion
Provides get, set, delete operations with TTL support.
"""

import json
import logging
import os
from typing import Any, Optional, Union

import redis.asyncio as aioredis

logger = logging.getLogger("Dominion.CacheService")


class CacheService:
    """
    Async Redis cache service with JSON serialization.
    
    Usage:
        cache = CacheService()
        await cache.set("key", {"data": "value"}, ttl=300)
        data = await cache.get("key")
        await cache.delete("key")
    """
    
    def __init__(self, redis_url: Optional[str] = None):
        """
        Initialize CacheService.
        
        Args:
            redis_url: Redis connection URL. Defaults to REDIS_URL env var.
        """
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._client: Optional[aioredis.Redis] = None
        self._enabled = True
    
    async def _get_client(self) -> aioredis.Redis:
        """Get or create Redis client connection."""
        if self._client is None:
            try:
                self._client = aioredis.from_url(
                    self._redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                # Test connection
                await self._client.ping()
                logger.info(f"CacheService connected to Redis: {self._redis_url}")
            except Exception as e:
                logger.warning(f"CacheService Redis connection failed: {e}")
                self._enabled = False
                raise
        return self._client
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value (deserialized from JSON) or None if not found
        """
        if not self._enabled:
            return None
            
        try:
            client = await self._get_client()
            value = await client.get(key)
            if value is None:
                return None
            # Try to deserialize JSON, fallback to raw string
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        except Exception as e:
            logger.warning(f"Cache get error for key '{key}': {e}")
            return None
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Set value in cache with optional TTL.
        
        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized if not a string)
            ttl: Time-to-live in seconds (None = no expiration)
            
        Returns:
            True if successful, False otherwise
        """
        if not self._enabled:
            return False
            
        try:
            client = await self._get_client()
            # Serialize value to JSON if not a string
            if isinstance(value, str):
                serialized = value
            else:
                serialized = json.dumps(value, ensure_ascii=False, default=str)
            
            if ttl is not None:
                await client.setex(key, ttl, serialized)
            else:
                await client.set(key, serialized)
            return True
        except Exception as e:
            logger.warning(f"Cache set error for key '{key}': {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """
        Delete value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if key was deleted, False otherwise
        """
        if not self._enabled:
            return False
            
        try:
            client = await self._get_client()
            result = await client.delete(key)
            return result > 0
        except Exception as e:
            logger.warning(f"Cache delete error for key '{key}': {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists, False otherwise
        """
        if not self._enabled:
            return False
            
        try:
            client = await self._get_client()
            return await client.exists(key) > 0
        except Exception as e:
            logger.warning(f"Cache exists error for key '{key}': {e}")
            return False
    
    async def clear_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern.
        
        Args:
            pattern: Redis key pattern (e.g., "garage:*")
            
        Returns:
            Number of keys deleted
        """
        if not self._enabled:
            return 0
            
        try:
            client = await self._get_client()
            keys = []
            async for key in client.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                return await client.delete(*keys)
            return 0
        except Exception as e:
            logger.warning(f"Cache clear_pattern error for '{pattern}': {e}")
            return 0
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("CacheService Redis connection closed")
    
    # =================================================================
    # DOMAIN-SPECIFIC HELPERS (for main.py compatibility)
    # =================================================================
    
    async def get_garage_stats(self, park: str) -> Optional[dict]:
        """Get cached garage statistics for a park."""
        return await self.get(f"garage:{park}:stats")
    
    async def set_garage_stats(self, stats: dict, park: str, ttl: int = 60) -> bool:
        """Set cached garage statistics for a park."""
        return await self.set(f"garage:{park}:stats", stats, ttl=ttl)
    
    async def get_driver_stats(self, driver_id: int) -> Optional[dict]:
        """Get cached driver statistics."""
        return await self.get(f"driver:{driver_id}:stats")
    
    async def set_driver_stats(self, driver_id: int, stats: dict, ttl: int = 60) -> bool:
        """Set cached driver statistics."""
        return await self.set(f"driver:{driver_id}:stats", stats, ttl=ttl)
    
    async def get_triad_data(self, park: str) -> Optional[dict]:
        """Get cached triad data for a park."""
        return await self.get(f"triad:{park}")
    
    async def set_triad_data(self, park: str, data: dict, ttl: int = 30) -> bool:
        """Set cached triad data for a park."""
        return await self.set(f"triad:{park}", data, ttl=ttl)


# Global singleton instance for import
cache_service = CacheService()