"""
HTTP Cache Headers Middleware
Legger til riktige cache headers for API responses
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable
import logging

logger = logging.getLogger(__name__)

class CacheHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware for å legge til HTTP cache headers basert på endpoint
    """
    
    # Cache-strategi per endpoint-type
    CACHE_STRATEGIES = {
        # Statiske data - lang cache
        'activity_types': {'max-age': 86400, 'public': True},  # 24 timer
        'summary': {'max-age': 3600, 'public': True},  # 1 time
        
        # Semi-statiske data - medium cache
        'activities': {'max-age': 300, 'public': False},  # 5 minutter
        'hrv': {'max-age': 300, 'public': False},  # 5 minutter
        'sleep': {'max-age': 300, 'public': False},  # 5 minutter
        'body_battery': {'max-age': 300, 'public': False},  # 5 minutter
        'stress': {'max-age': 300, 'public': False},  # 5 minutter
        
        # Analyse-data - medium cache
        'analysis': {'max-age': 600, 'public': False},  # 10 minutter
        'vo2max': {'max-age': 600, 'public': False},  # 10 minutter
        'running_economy': {'max-age': 600, 'public': False},  # 10 minutter
        
        # Dynamiske data - kort cache
        'sync': {'max-age': 0, 'public': False, 'no-store': True},  # Ingen cache
        'cache': {'max-age': 0, 'public': False, 'no-store': True},  # Ingen cache
        'bulk': {'max-age': 0, 'public': False, 'no-store': True},  # Ingen cache
    }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Prosesser request og legg til cache headers på response
        """
        # Kjør request
        response = await call_next(request)
        
        # Kun cache GET requests
        if request.method != 'GET':
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
        
        # Finn cache-strategi basert på path
        cache_strategy = self._get_cache_strategy(request.url.path)
        
        if cache_strategy:
            # Bygg Cache-Control header
            cache_control_parts = []
            
            if cache_strategy.get('no-store'):
                cache_control_parts.append('no-store')
                cache_control_parts.append('no-cache')
                cache_control_parts.append('must-revalidate')
            else:
                max_age = cache_strategy.get('max-age', 0)
                
                if cache_strategy.get('public'):
                    cache_control_parts.append('public')
                else:
                    cache_control_parts.append('private')
                
                cache_control_parts.append(f'max-age={max_age}')
                
                # Legg til stale-while-revalidate for bedre UX
                # Tillater å bruke gammel cache mens ny hentes
                if max_age > 0:
                    stale_while_revalidate = max_age // 2  # Halvparten av max-age
                    cache_control_parts.append(f'stale-while-revalidate={stale_while_revalidate}')
            
            cache_control = ', '.join(cache_control_parts)
            response.headers['Cache-Control'] = cache_control
            
            # Legg til ETag for validering
            # ETag genereres basert på response content (hvis det er praktisk)
            if not cache_strategy.get('no-store'):
                # For produksjon, generer ETag basert på content hash
                # For nå, bruk en placeholder
                response.headers['ETag'] = f'W/"{hash(request.url.path)}"'
                
                # Legg til Vary header for at cache skal respektere query params
                response.headers['Vary'] = 'Accept-Encoding'
            
            logger.debug(f"Cache headers for {request.url.path}: {cache_control}")
        
        return response
    
    def _get_cache_strategy(self, path: str) -> dict:
        """
        Finn cache-strategi basert på request path
        """
        # Fjern leading slash og split på /
        path_parts = path.strip('/').split('/')
        
        # Finn relevant endpoint type
        for endpoint_type, strategy in self.CACHE_STRATEGIES.items():
            if endpoint_type in path:
                return strategy
        
        # Default: Kort cache for alle andre endpoints
        return {'max-age': 60, 'public': False}  # 1 minutt default
















