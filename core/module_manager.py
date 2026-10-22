"""Cycle explicite des extensions. Désactivé signifie non importé."""

from dataclasses import dataclass, field
import copy
import importlib
import json
import logging
from pathlib import Path
from core.module import ModuleManifest, RedModule
from core.capabilities import Capability
from core.capability_errors import ModuleConfigurationError

LOG = logging.getLogger("assistant.modules")


class ModuleAPI:
    def __init__(self, runtime, manifest, config):
        self.runtime, self.manifest = runtime, manifest
        self.config = copy.deepcopy(config)
        self.settings = runtime.config if hasattr(runtime, "config") else None
        self.logger = logging.getLogger(f"assistant.modules.{manifest.id}")
        self.capabilities = runtime.capabilities
        self._cleanup = []
        self.admin_routes = []
        self.active = True

    def publish(self, name, value):
        self.capabilities.publish(name, value, self.manifest.id)

    def route(self, handler, priority=100):
        self.capabilities.add_route(self.manifest.id, handler, priority)

    def select_domains(self, handler):
        self.capabilities.add_selector(self.manifest.id, handler)

    def adopt_tool(self, tool, *, name, aliases=(), intents=()):
        """Conserve le schéma, le nom de permission et l'implémentation existants."""
        return self.capabilities.register(Capability(
            name, tool, self.manifest.id, tuple(dict.fromkeys((tool.nom, *aliases)))
            if name != tool.nom else tuple(aliases), tuple(intents)))

    def capability(self, function, *, name, description, arguments=None,
                   security_level="N1", aliases=(), intents=(), announcement=None):
        tool_name = name.replace(".", "_")
        tool = self.register_tool(function, name=tool_name, description=description, expose=False,
                                 parametres=arguments, permission_level=security_level,
                                 annonce=announcement)
        return self.adopt_tool(tool, name=name, aliases=aliases, intents=intents)

    def subscribe(self, event_name, handler):
        def receive(event):
            if event.name == event_name:
                handler(event)

        unsubscribe = self.runtime.events.subscribe(receive)
        self._cleanup.append(unsubscribe)
        return unsubscribe

    def register_tool(self, function, *, name, description, expose=True, **metadata):
        from core import registre

        if registre.get(name):
            raise ValueError(f"Outil déjà présent : {name}")
        registre.outil(nom=name, description=description, **metadata)(function)
        registered = registre.get(name)
        registered.extension = self.manifest.id
        self._cleanup.append(lambda: registre.retirer(name, registered))
        if expose:
            self.adopt_tool(registered, name=name)
        return registered

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
            try:
                manifest = ModuleManifest.parse(json.loads(file.read_text(encoding="utf8")))
            except Exception as error:
                manifest = ModuleManifest(file.parent.name, "?", "Manifeste invalide", "", name=file.parent.name)
                self.records[file.parent.name] = ModuleRecord(manifest, state="FAILED", error=type(error).__name__)
                LOG.error("Manifeste invalide : %s", file.parent.name)
                continue
            if manifest.id != file.parent.name:
                self.records[file.parent.name] = ModuleRecord(manifest, state="FAILED", error="ModuleIdentityMismatch")
                continue
            if manifest.id in self.records:
                raise ValueError("Module déclaré deux fois.")
            conf = self.config.get(manifest.id, {})
            if not isinstance(conf, dict):
                self.records[manifest.id] = ModuleRecord(manifest, state="NOT_CONFIGURED", error="ModuleConfigurationError")
                continue
            self.records[manifest.id] = ModuleRecord(
                manifest, enabled=conf.get("enabled", False) is True
            )
            self.runtime.capabilities.claimed_tool_modules.update(manifest.legacy_tool_modules)
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
                    r.state = "NOT_CONFIGURED" if isinstance(e, ModuleConfigurationError) else "FAILED"
                    r.error = type(e).__name__
                    LOG.error("Module %s indisponible (%s)", r.manifest.id, r.error)
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
            h = {"ok": not r.enabled, "state": r.state, "enabled": r.enabled,
                 "name": r.manifest.name or ident, "version": r.manifest.version,
                 "description": r.manifest.description,
                 "status": "DISABLED" if not r.enabled and not r.error else {
                     "STARTED": "ACTIVE", "FAILED": "ERROR"}.get(r.state, r.state),
                 "capability_count": len(self.runtime.capabilities.actions(ident))}
            if r.state == "STARTED":
                try:
                    h.update(r.instance.health())
                except Exception:
                    h.update(ok=False, error="HealthCheckFailed")
            if r.error:
                h.update(ok=False, error=r.error)
            result[ident] = h
        return result
