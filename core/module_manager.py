"""Cycle explicite des extensions. Désactivé signifie non importé."""

from dataclasses import dataclass, field
import copy
import importlib
import json
from pathlib import Path
from core.module import ModuleManifest, RedModule


class ModuleAPI:
    def __init__(self, runtime, manifest, config):
        self.runtime, self.manifest = runtime, manifest
        self.config = copy.deepcopy(config)
        self.capabilities = runtime.capabilities
        self._cleanup = []
        self.admin_routes = []
        self.active = True

    def publish(self, name, value):
        self.capabilities.publish(name, value, self.manifest.id)

    def subscribe(self, event_name, handler):
        def receive(event):
            if event.name == event_name:
                handler(event)

        unsubscribe = self.runtime.events.subscribe(receive)
        self._cleanup.append(unsubscribe)
        return unsubscribe

    def register_tool(self, function, *, name, description, **metadata):
        from core import registre

        if registre.get(name):
            raise ValueError(f"Outil déjà présent : {name}")
        registre.outil(nom=name, description=description, **metadata)(function)
        registered = registre.get(name)
        registered.extension = self.manifest.id
        self._cleanup.append(lambda: registre.retirer(name, registered))

    def on_stop(self, cleanup):
        """Rattacher la fermeture d'un worker, watcher ou scheduler au module."""
        self._cleanup.append(cleanup)

    def admin_endpoint(self, path, endpoint, methods=("GET",)):
        if not path.startswith("/") or ".." in path:
            raise ValueError("Chemin administratif invalide.")
        from functools import wraps
        import inspect

        if inspect.iscoroutinefunction(endpoint):

            @wraps(endpoint)
            async def guarded(*args, **kwargs):
                if not self.active:
                    from fastapi import HTTPException
                    raise HTTPException(503, "Module arrêté.")
                return await endpoint(*args, **kwargs)

        else:

            @wraps(endpoint)
            def guarded(*args, **kwargs):
                if not self.active:
                    from fastapi import HTTPException
                    raise HTTPException(503, "Module arrêté.")
                return endpoint(*args, **kwargs)

        self.admin_routes.append(
            (f"/api/panneau/modules/{self.manifest.id}{path}", guarded, tuple(methods))
        )

    def close(self):
        self.active = False
        failures = []
        for close in reversed(self._cleanup):
            try:
                close()
            except Exception as e:
                failures.append(type(e).__name__)
        self._cleanup.clear()
        self.admin_routes.clear()
        self.capabilities.remove_owner(self.manifest.id)
        return failures


@dataclass
class ModuleRecord:
    manifest: ModuleManifest
    state: str = "DISCOVERED"
    enabled: bool = False
    instance: object = None
    api: object = None
    error: str | None = None


class ModuleManager:
    def __init__(self, runtime, folder, config=None):
        self.runtime, self.folder, self.config = runtime, Path(folder), config or {}
        self.records = {}
        self._order = []

    def discover(self):
        for file in sorted(self.folder.glob("*/manifest.json")):
            manifest = ModuleManifest.parse(json.loads(file.read_text(encoding="utf8")))
            if manifest.id != file.parent.name:
                raise ValueError("Nom de dossier et id de module différents.")
            if manifest.id in self.records:
                raise ValueError("Module déclaré deux fois.")
            conf = self.config.get(manifest.id, {})
            if not isinstance(conf, dict):
                raise ValueError(f"Configuration du module {manifest.id} invalide.")
            self.records[manifest.id] = ModuleRecord(
                manifest, enabled=conf.get("enabled", False) is True
            )
        return self.records

    def start(self):
        if not self.records:
            self.discover()
        pending = [
            r
            for r in self.records.values()
            if r.enabled and r.state in {"DISCOVERED", "STOPPED"}
        ]
        while pending:
            progressed = False
            for r in tuple(pending):
                if any(
                    self.runtime.capabilities.get(c) is None
                    for c in r.manifest.required_capabilities
                ):
                    continue
                pending.remove(r)
                progressed = True
                try:
                    mod, cls = r.manifest.entrypoint.split(":")
                    r.instance = getattr(importlib.import_module(mod), cls)()
                    if not isinstance(r.instance, RedModule):
                        raise TypeError("Extension sans contrat RedModule.")
                    r.api = ModuleAPI(
                        self.runtime, r.manifest, self.config.get(r.manifest.id, {})
                    )
                    r.instance.register(r.api)
                    r.state = "REGISTERED"
                    r.instance.start()
                    r.state = "STARTED"
                    self._order.append(r)
                except Exception as e:
                    if r.instance:
                        try:
                            r.instance.stop()
                        except Exception:
                            pass
                    if r.api:
                        r.api.close()
                    r.state = "FAILED"
                    r.error = type(e).__name__
            if not progressed:
                for r in pending:
                    r.state = "FAILED"
                    r.error = "RequiredCapabilityMissing"
                break

    def stop(self):
        for r in reversed(self._order):
            try:
                r.instance.stop()
            except Exception as e:
                r.error = type(e).__name__
            finally:
                r.api.close()
                r.state = "STOPPED"
        self._order.clear()

    def health(self):
        result = {}
        for ident, r in self.records.items():
            h = {"ok": not r.enabled, "state": r.state, "enabled": r.enabled}
            if r.state == "STARTED":
                try:
                    h.update(r.instance.health())
                except Exception:
                    h.update(ok=False, error="HealthCheckFailed")
            if r.error:
                h.update(ok=False, error=r.error)
            result[ident] = h
        return result
