"""DEPRECATED : importer services.tts.factory."""
import sys
from importlib import import_module
sys.modules[__name__]=import_module('services.tts.factory')
