"""
Cache Manager for Treningsanalyse
Provides hybrid caching: Redis (persistent) + in-memory (fast fallback)
"""
from functools import lru_cache
from typing import Optional, Dict, Any
import hashlib
import json
import logging
from .redis_cache import get_redis_cache, RedisCache

logger = logging.getLogger(__name__)

class CacheManager:
    """Manages caching for TSS, power calculations, and summaries with Redis + in-memory fallback"""
    
    def __init__(self, max_size: int = 1000, use_redis: bool = True):
        self.max_size = max_size
        self.use_redis = use_redis
        
        # In-memory cache (fallback)
        self._tss_cache: Dict[str, float] = {}
        self._power_cache: Dict[str, Dict[str, Any]] = {}
        self._summary_cache: Dict[str, Any] = {}
        
        # Redis cache (persistent)
        self.redis: Optional[RedisCache] = None
        if use_redis:
            try:
                self.redis = get_redis_cache()
                if self.redis.is_available():
                    logger.info("Redis cache aktivert for CacheManager")
                else:
                    logger.info("Redis ikke tilgjengelig, bruker kun in-memory cache")
                    self.redis = None
            except Exception as e:
                logger.warning(f"Kunne ikke aktivere Redis: {e}. Bruker in-memory cache.")
                self.redis = None
    
    def get_cache_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate a unique cache key from arguments"""
        # Kombiner prefix med args og kwargs
        data = {
            'prefix': prefix,
            'args': args,
            'kwargs': sorted(kwargs.items())
        }
        # Generer MD5 hash for konsistent cache key
        key_string = json.dumps(data, sort_keys=True, default=str)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get_tss(self, activity_id: str) -> Optional[float]:
        """Hent TSS fra cache (Redis først, deretter in-memory)"""
        # Prøv Redis først
        if self.redis and self.redis.is_available():
            key = f"tss:{activity_id}"
            value = self.redis.get(key)
            if value is not None:
                logger.debug(f"TSS cache hit (Redis) for activity {activity_id}")
                return value
        
        # Fallback til in-memory
        value = self._tss_cache.get(activity_id)
        if value is not None:
            logger.debug(f"TSS cache hit (memory) for activity {activity_id}")
        return value
    
    def set_tss(self, activity_id: str, tss_value: float):
        """Lagre TSS i cache (både Redis og in-memory)"""
        # Lagre i Redis
        if self.redis and self.redis.is_available():
            key = f"tss:{activity_id}"
            self.redis.set(key, tss_value, ttl=86400)  # 24 timer TTL
        
        # Lagre i in-memory cache
        if len(self._tss_cache) >= self.max_size:
            # Fjern eldste entry hvis cache er full (FIFO)
            first_key = next(iter(self._tss_cache))
            del self._tss_cache[first_key]
        self._tss_cache[activity_id] = tss_value
        logger.debug(f"Cached TSS for activity {activity_id}: {tss_value}")
    
    def get_power(self, activity_id: str) -> Optional[Dict[str, Any]]:
        """Hent power-beregning fra cache (Redis først, deretter in-memory)"""
        # Prøv Redis først
        if self.redis and self.redis.is_available():
            key = f"power:{activity_id}"
            value = self.redis.get(key)
            if value is not None:
                logger.debug(f"Power cache hit (Redis) for activity {activity_id}")
                return value
        
        # Fallback til in-memory
        value = self._power_cache.get(activity_id)
        if value is not None:
            logger.debug(f"Power cache hit (memory) for activity {activity_id}")
        return value
    
    def set_power(self, activity_id: str, power_data: Dict[str, Any]):
        """Lagre power-beregning i cache (både Redis og in-memory)"""
        # Lagre i Redis
        if self.redis and self.redis.is_available():
            key = f"power:{activity_id}"
            self.redis.set(key, power_data, ttl=86400)  # 24 timer TTL
        
        # Lagre i in-memory cache
        if len(self._power_cache) >= self.max_size:
            # Fjern eldste entry hvis cache er full (FIFO)
            first_key = next(iter(self._power_cache))
            del self._power_cache[first_key]
        self._power_cache[activity_id] = power_data
        logger.debug(f"Cached power for activity {activity_id}")
    
    def get_summary(self, cache_key: str) -> Optional[Any]:
        """Hent summary fra cache"""
        return self._summary_cache.get(cache_key)
    
    def set_summary(self, cache_key: str, summary_data: Any, ttl_seconds: int = 3600):
        """Lagre summary i cache med TTL"""
        if len(self._summary_cache) >= self.max_size:
            # Fjern eldste entry hvis cache er full (FIFO)
            first_key = next(iter(self._summary_cache))
            del self._summary_cache[first_key]
        self._summary_cache[cache_key] = {
            'data': summary_data,
            'timestamp': __import__('time').time(),
            'ttl': ttl_seconds
        }
        logger.debug(f"Cached summary with key {cache_key}")
    
    def is_summary_valid(self, cache_key: str) -> bool:
        """Sjekk om cached summary er fortsatt gyldig (ikke utløpt)"""
        if cache_key not in self._summary_cache:
            return False
        
        cached = self._summary_cache[cache_key]
        import time
        age = time.time() - cached['timestamp']
        return age < cached['ttl']
    
    def clear_cache(self, cache_type: Optional[str] = None):
        """Tøm cache. Hvis cache_type er spesifisert, tøm kun den typen."""
        if cache_type == 'tss':
            self._tss_cache.clear()
            logger.info("TSS cache cleared")
        elif cache_type == 'power':
            self._power_cache.clear()
            logger.info("Power cache cleared")
        elif cache_type == 'summary':
            self._summary_cache.clear()
            logger.info("Summary cache cleared")
        else:
            # Tøm alt
            self._tss_cache.clear()
            self._power_cache.clear()
            self._summary_cache.clear()
            logger.info("All caches cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Få statistikk over cache-bruk (både Redis og in-memory)"""
        stats = {
            'memory': {
                'tss_count': len(self._tss_cache),
                'power_count': len(self._power_cache),
                'summary_count': len(self._summary_cache),
                'total': len(self._tss_cache) + len(self._power_cache) + len(self._summary_cache)
            }
        }
        
        # Legg til Redis stats hvis tilgjengelig
        if self.redis and self.redis.is_available():
            stats['redis'] = self.redis.get_stats()
        else:
            stats['redis'] = {'enabled': False, 'status': 'not_available'}
        
        return stats


# Global cache instance
_cache_manager: Optional[CacheManager] = None

def get_cache_manager() -> CacheManager:
    """Get or create global cache manager instance"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager(max_size=1000)
        logger.info("Cache manager initialized")
    return _cache_manager



