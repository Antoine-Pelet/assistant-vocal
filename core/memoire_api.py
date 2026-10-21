"""DEPRECATED : importer interfaces.admin.memory_api."""
import sys
from importlib import import_module
sys.modules[__name__]=import_module('interfaces.admin.memory_api')
