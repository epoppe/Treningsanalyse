"""
Forbedret feilhåndtering og logging system.
"""

import logging
import traceback
import sys
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

class ErrorHandler:
    """Sentralisert feilhåndtering."""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.setup_logging()
    
    def setup_logging(self):
        """Sett opp logging konfiguration."""
        log_file = self.log_dir / f"treningsanalyse_{datetime.now().strftime('%Y%m%d')}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        self.logger = logging.getLogger(__name__)
    
    def log_error(self, error: Exception, context: Optional[Dict[str, Any]] = None):
        """Logg en feil med kontekst."""
        error_info = {
            'error_type': type(error).__name__,
            'error_message': str(error),
            'traceback': traceback.format_exc(),
            'timestamp': datetime.now().isoformat()
        }
        
        if context:
            error_info['context'] = context
        
        self.logger.error(f"Feil oppstod: {error_info}")
        
        # Skriv detaljert feilrapport til fil
        error_file = self.log_dir / f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(error_file, 'w', encoding='utf-8') as f:
            f.write(f"Feilrapport - {datetime.now()}\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Feiltype: {error_info['error_type']}\n")
            f.write(f"Melding: {error_info['error_message']}\n\n")
            f.write("Traceback:\n")
            f.write(error_info['traceback'])
            
            if context:
                f.write(f"\nKontekst:\n")
                for key, value in context.items():
                    f.write(f"  {key}: {value}\n")
    
    def log_info(self, message: str, extra_data: Optional[Dict[str, Any]] = None):
        """Logg informasjon."""
        log_message = message
        if extra_data:
            log_message += f" - Data: {extra_data}"
        self.logger.info(log_message)
    
    def log_warning(self, message: str, extra_data: Optional[Dict[str, Any]] = None):
        """Logg advarsel."""
        log_message = message
        if extra_data:
            log_message += f" - Data: {extra_data}"
        self.logger.warning(log_message)

# Global error handler
error_handler = ErrorHandler()

def handle_api_error(func):
    """Decorator for API-feilhåndtering."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_handler.log_error(e, {
                'function': func.__name__,
                'args': str(args),
                'kwargs': str(kwargs)
            })
            raise
    return wrapper 