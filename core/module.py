"""Contrat d'extension : les manifests se lisent sans importer les modules."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ModuleManifest:
    id: str
    version: str
    description: str
    entrypoint: str
    required_capabilities: tuple = ()
    optional_capabilities: tuple = ()

    @classmethod
    def parse(cls, raw):
        if not isinstance(raw, dict):
            raise ValueError("Manifeste invalide.")
        ident = raw.get("id", "")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", ident):
            raise ValueError("Identifiant de module invalide.")
        entry = raw.get("entrypoint", f"modules.{ident}.module:Module")
        if not re.fullmatch(
            rf"modules\.{ident}\.[a-zA-Z0-9_.]+:[A-Za-z_][A-Za-z0-9_]*", entry
        ):
            raise ValueError("Le point d’entrée doit appartenir au package du module.")
        arrays = []
        for key in ("required_capabilities", "optional_capabilities"):
            values = raw.get(key, [])
            if not isinstance(values, list) or any(
                not isinstance(v, str) or not re.fullmatch(r"[a-z][a-z0-9_.]+", v)
                for v in values
            ):
                raise ValueError(f"{key} invalide.")
            arrays.append(tuple(values))
        return cls(ident, str(raw["version"]), str(raw["description"]), entry, *arrays)


class RedModule:
    def register(self, app):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def health(self):
        return {"ok": True}
