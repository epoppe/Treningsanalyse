"""
Plugin system for å utvide treningsanalyse-funksjonalitet.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
import importlib
import os

class BasePlugin(ABC):
    """Base class for alle plugins."""
    
    @abstractmethod
    def get_name(self) -> str:
        """Returner plugin-navn."""
        pass
    
    @abstractmethod
    def process_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Prosesser data og returner resultat."""
        pass
    
    @abstractmethod
    def get_supported_data_types(self) -> List[str]:
        """Returner liste over støttede datatyper."""
        pass

class PluginManager:
    """Manager for å laste og kjøre plugins."""
    
    def __init__(self):
        self.plugins: Dict[str, BasePlugin] = {}
    
    def load_plugins(self, plugin_dir: str = "plugins"):
        """Last inn alle plugins fra en mappe."""
        plugin_path = os.path.join(os.path.dirname(__file__), plugin_dir)
        
        if not os.path.exists(plugin_path):
            return
        
        for filename in os.listdir(plugin_path):
            if filename.endswith('.py') and not filename.startswith('__'):
                module_name = filename[:-3]
                try:
                    module = importlib.import_module(f"app.plugins.{plugin_dir}.{module_name}")
                    # Finn plugin-klasser i modulet
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and 
                            issubclass(attr, BasePlugin) and 
                            attr != BasePlugin):
                            plugin = attr()
                            self.plugins[plugin.get_name()] = plugin
                except Exception as e:
                    print(f"Kunne ikke laste plugin {module_name}: {e}")
    
    def get_plugin(self, name: str) -> BasePlugin:
        """Hent en spesifikk plugin."""
        return self.plugins.get(name)
    
    def process_with_plugins(self, data_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Prosesser data med alle relevante plugins."""
        result = data.copy()
        
        for plugin in self.plugins.values():
            if data_type in plugin.get_supported_data_types():
                try:
                    result = plugin.process_data(result)
                except Exception as e:
                    print(f"Feil i plugin {plugin.get_name()}: {e}")
        
        return result

# Global plugin manager
plugin_manager = PluginManager() 