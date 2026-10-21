"""DEPRECATED : importer services.llm.factory."""
import sys
from importlib import import_module
sys.modules[__name__]=import_module('services.llm.factory')
