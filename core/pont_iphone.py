"""DEPRECATED : importer transports.iphone.server."""
import sys
from importlib import import_module
sys.modules[__name__]=import_module('transports.iphone.server')
