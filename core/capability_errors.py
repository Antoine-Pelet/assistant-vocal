"""Erreurs publiques des extensions, sans dépendance technique."""


class CapabilityExecutionError(RuntimeError):
    pass


class ModuleConfigurationError(ValueError):
    pass
