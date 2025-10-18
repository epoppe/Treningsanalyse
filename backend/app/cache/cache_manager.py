"""
Cache Manager for Treningsanalyse
Provides in-memory LRU caching for expensive computations
"""
from functools import lru_cache
from typing import Optional, Dict, Any
import hashlib
import json
import logging

logger = logging.getLogger(__name__)

class CacheManager:
    """Manages caching for TSS, power calculations, and summaries"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._tss_cache: Dict[str, float] = {}
        self._power_cache: Dict[str, Dict[str, Any]] = {}
        self._summary_cache: Dict[str, Any] = {}
    
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
        """Hent TSS fra cache"""
        return self._tss_cache.get(activity_id)
    
    def set_tss(self, activity_id: str, tss_value: float):
        """Lagre TSS i cache"""
        if len(self._tss_cache) >= self.max_size:
            # Fjern eldste entry hvis cache er full (FIFO)
            first_key = next(iter(self._tss_cache))
            del self._tss_cache[first_key]
        self._tss_cache[activity_id] = tss_value
        logger.debug(f"Cached TSS for activity {activity_id}: {tss_value}")
    
    def get_power(self, activity_id: str) -> Optional[Dict[str, Any]]:
        """Hent power-beregning fra cache"""
        return self._power_cache.get(activity_id)
    
    def set_power(self, activity_id: str, power_data: Dict[str, Any]):
        """Lagre power-beregning i cache"""
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
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Få statistikk over cache-bruk"""
        return {
            'tss_count': len(self._tss_cache),
            'power_count': len(self._power_cache),
            'summary_count': len(self._summary_cache),
            'total': len(self._tss_cache) + len(self._power_cache) + len(self._summary_cache)
        }


# Global cache instance
_cache_manager: Optional[CacheManager] = None

def get_cache_manager() -> CacheManager:
    """Get or create global cache manager instance"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager(max_size=1000)
        logger.info("Cache manager initialized")
    return _cache_manager

