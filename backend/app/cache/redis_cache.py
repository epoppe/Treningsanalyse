"""
Redis Cache Implementation for Treningsanalyse
Provides persistent, distributed caching with TTL support
"""
import redis
import json
import logging
from typing import Optional, Any, Dict
from datetime import timedelta

logger = logging.getLogger(__name__)

class RedisCache:
    """Redis-basert cache med JSON serialisering og TTL"""
    
    def __init__(
        self, 
        host: str = 'localhost', 
        port: int = 6379, 
        db: int = 0,
        password: Optional[str] = None,
        decode_responses: bool = True
    ):
        """
        Initialiserer Redis-tilkobling
        
        Args:
            host: Redis server hostname
            port: Redis server port
            db: Redis database nummer (0-15)
            password: Redis password (hvis konfigurert)
            decode_responses: Dekoder responses til strings
        """
        try:
            self.client = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=decode_responses,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            # Test connection
            self.client.ping()
            self.enabled = True
            logger.info(f"Redis cache initialisert: {host}:{port} (db={db})")
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Kunne ikke koble til Redis: {e}. Fallback til in-memory cache.")
            self.client = None
            self.enabled = False
    
    def is_available(self) -> bool:
        """Sjekk om Redis er tilgjengelig"""
        if not self.enabled:
            return False
        try:
            return self.client.ping()
        except:
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """
        Hent verdi fra cache
        
        Args:
            key: Cache key
            
        Returns:
            Cachet verdi eller None hvis ikke funnet
        """
        if not self.enabled:
            return None
            
        try:
            value = self.client.get(key)
            if value is None:
                return None
            return json.loads(value)
        except Exception as e:
            logger.warning(f"Feil ved henting fra Redis cache (key={key}): {e}")
            return None
    
    def set(
        self, 
        key: str, 
        value: Any, 
        ttl: int = 3600,
        nx: bool = False,
        xx: bool = False
    ) -> bool:
        """
        Lagre verdi i cache med TTL
        
        Args:
            key: Cache key
            value: Verdi å cache (må være JSON-serialiserbar)
            ttl: Time to live i sekunder (default 1 time)
            nx: Set only if not exists
            xx: Set only if exists
            
        Returns:
            True hvis vellykket, False ellers
        """
        if not self.enabled:
            return False
            
        try:
            serialized = json.dumps(value, default=str)
            result = self.client.setex(
                key, 
                timedelta(seconds=ttl), 
                serialized
            )
            return result
        except Exception as e:
            logger.warning(f"Feil ved lagring i Redis cache (key={key}): {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """
        Slett key fra cache
        
        Args:
            key: Cache key
            
        Returns:
            True hvis slettet, False ellers
        """
        if not self.enabled:
            return False
            
        try:
            return self.client.delete(key) > 0
        except Exception as e:
            logger.warning(f"Feil ved sletting fra Redis cache (key={key}): {e}")
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """
        Slett alle keys som matcher pattern
        
        Args:
            pattern: Pattern (f.eks. "activities:*")
            
        Returns:
            Antall slettede keys
        """
        if not self.enabled:
            return 0
            
        try:
            keys = self.client.keys(pattern)
            if keys:
                return self.client.delete(*keys)
            return 0
        except Exception as e:
            logger.warning(f"Feil ved sletting av pattern fra Redis (pattern={pattern}): {e}")
            return 0
    
    def exists(self, key: str) -> bool:
        """Sjekk om key eksisterer"""
        if not self.enabled:
            return False
        try:
            return self.client.exists(key) > 0
        except:
            return False
    
    def get_ttl(self, key: str) -> int:
        """Hent gjenværende TTL i sekunder (-2 hvis ikke eksisterer, -1 hvis ingen TTL)"""
        if not self.enabled:
            return -2
        try:
            return self.client.ttl(key)
        except:
            return -2
    
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Inkrementer en verdi atomisk"""
        if not self.enabled:
            return None
        try:
            return self.client.incrby(key, amount)
        except:
            return None
    
    def get_multiple(self, keys: list[str]) -> Dict[str, Any]:
        """
        Hent flere verdier på en gang (pipeline)
        
        Args:
            keys: Liste med cache keys
            
        Returns:
            Dict med key: value par
        """
        if not self.enabled or not keys:
            return {}
            
        try:
            pipeline = self.client.pipeline()
            for key in keys:
                pipeline.get(key)
            values = pipeline.execute()
            
            result = {}
            for key, value in zip(keys, values):
                if value is not None:
                    try:
                        result[key] = json.loads(value)
                    except:
                        pass
            return result
        except Exception as e:
            logger.warning(f"Feil ved bulk-henting fra Redis: {e}")
            return {}
    
    def set_multiple(self, items: Dict[str, Any], ttl: int = 3600) -> int:
        """
        Lagre flere verdier på en gang (pipeline)
        
        Args:
            items: Dict med key: value par
            ttl: Time to live i sekunder
            
        Returns:
            Antall vellykkede operasjoner
        """
        if not self.enabled or not items:
            return 0
            
        try:
            pipeline = self.client.pipeline()
            for key, value in items.items():
                serialized = json.dumps(value, default=str)
                pipeline.setex(key, timedelta(seconds=ttl), serialized)
            results = pipeline.execute()
            return sum(1 for r in results if r)
        except Exception as e:
            logger.warning(f"Feil ved bulk-lagring i Redis: {e}")
            return 0
    
    def clear_all(self) -> bool:
        """
        Tøm hele databasen (FARLIG - bruk med forsiktighet!)
        
        Returns:
            True hvis vellykket
        """
        if not self.enabled:
            return False
            
        try:
            self.client.flushdb()
            logger.info("Redis database tømt")
            return True
        except Exception as e:
            logger.error(f"Feil ved tømming av Redis: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Hent cache-statistikk
        
        Returns:
            Dict med statistikk
        """
        if not self.enabled:
            return {
                'enabled': False,
                'status': 'disabled'
            }
            
        try:
            info = self.client.info()
            return {
                'enabled': True,
                'status': 'connected',
                'used_memory_human': info.get('used_memory_human', 'N/A'),
                'total_commands_processed': info.get('total_commands_processed', 0),
                'connected_clients': info.get('connected_clients', 0),
                'keys_count': self.client.dbsize(),
                'hit_rate': self._calculate_hit_rate(info)
            }
        except Exception as e:
            logger.error(f"Feil ved henting av Redis stats: {e}")
            return {
                'enabled': False,
                'status': 'error',
                'error': str(e)
            }
    
    def _calculate_hit_rate(self, info: Dict) -> float:
        """Beregn cache hit rate"""
        hits = info.get('keyspace_hits', 0)
        misses = info.get('keyspace_misses', 0)
        total = hits + misses
        if total == 0:
            return 0.0
        return (hits / total) * 100


# Global Redis cache instance
_redis_cache: Optional[RedisCache] = None

def get_redis_cache(
    host: str = 'localhost',
    port: int = 6379,
    db: int = 0,
    password: Optional[str] = None
) -> RedisCache:
    """
    Get eller opprett global Redis cache instance
    
    Args:
        host: Redis server hostname
        port: Redis server port  
        db: Redis database nummer
        password: Redis password
        
    Returns:
        RedisCache instance
    """
    global _redis_cache
    if _redis_cache is None:
        _redis_cache = RedisCache(host, port, db, password)
    return _redis_cache

