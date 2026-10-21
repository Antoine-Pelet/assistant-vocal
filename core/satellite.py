"""DEPRECATED : importer transports.satellite.server."""
import sys
from importlib import import_module
sys.modules[__name__]=import_module('transports.satellite.server')
