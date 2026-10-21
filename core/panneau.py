"""DEPRECATED : importer interfaces.admin.service."""
import sys
from importlib import import_module
sys.modules[__name__]=import_module('interfaces.admin.service')
