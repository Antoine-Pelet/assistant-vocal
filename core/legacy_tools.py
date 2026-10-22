"""Adaptation à la demande des anciens outils ; aucun catalogue statique."""


class LegacyToolAdapter:
    def __init__(self, registry):
        self.registry = registry

    def resolve(self, name):
        from core import registre
        from core.capabilities import Capability

        tool = registre.get(name)
        if tool is None or getattr(tool, "extension", None):
            return None
        if getattr(tool, "module", None) in self.registry.claimed_tool_modules:
            return None
        return Capability(name, tool, "legacy_tools", registry=self.registry)

    def all(self):
        from core import registre

        return [c for t in registre.tous() if (c := self.resolve(t.nom))]
