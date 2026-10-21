"""DEPRECATED : importer services.tts.profiles."""
import sys
from importlib import import_module
sys.modules[__name__]=import_module('services.tts.profiles')
