"""DEPRECATED : importer core.tool_registry ; API outil conservée."""
import sys
from core import tool_registry
sys.modules[__name__]=tool_registry
