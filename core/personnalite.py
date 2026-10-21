"""DEPRECATED : importer conversation.persona."""
import sys
from importlib import import_module
sys.modules[__name__]=import_module('conversation.persona')
