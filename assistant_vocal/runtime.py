"""Composition minimale. Les moteurs lourds restent paresseux."""

from pathlib import Path
from core.capabilities import CapabilityRegistry
from core.module_manager import ModuleManager


class _DeviceAccess:
    """Keep the capability valid when room/device configuration changes."""

    def __init__(self, runtime):
        self.runtime = runtime

    def __getattr__(self, name):
        return getattr(self.runtime.devices, name)


class Runtime:
    def __init__(self):
        from core import config, memoire, registre
        from core.evenements import bus
        from core.maison import devices
        from security import authorization

        self.security = authorization
        self.config = config
        self.memory = memoire
        self.tools = registre
        self.events = bus
        self.capabilities = CapabilityRegistry()
        self._devices = devices
        self.started = False
        self.modules = None

    @property
    def devices(self):
        return self._devices()

    @property
    def llm(self):
        from core.llm import llm

        return llm()

    @property
    def tts(self):
        from core.tts import tts

        return tts()

    @property
    def stt(self):
        from services.stt.faster_whisper import service

        return service()

    def start(self):
        if self.started:
            return
        self.tools.charger_outils()
        self.devices  # valide le catalogue sans commander les appareils
        self.capabilities.publish("home.devices", _DeviceAccess(self), "runtime")
        self.capabilities.publish("events.local", self.events, "runtime")
        self.modules = ModuleManager(
            self,
            Path(__file__).resolve().parents[1] / "modules",
            self.config.reglage("modules", {}),
        )
        try:
            self.modules.start()
        except Exception:
            self.modules.stop()
            self.capabilities.remove_owner("runtime")
            raise
        self.started = True

    def stop(self):
        import sys
        import logging
        from core import tts, memoire, llm, voix
        from services.stt.faster_whisper import close
        from conversation.manager import manager

        cleanups = [self.modules.stop] if self.modules else []
        if "interfaces.server" in sys.modules:
            from interfaces import server

            cleanups.append(server.arreter)
        cleanups.extend(
            [manager.close_all, tts.reinitialiser, llm.reinitialiser, close]
        )
        voix.definir_parleur(None)
        if memoire._MAGASIN:
            cleanups.append(memoire._MAGASIN.fermer)
        for cleanup in cleanups:
            try:
                cleanup()
            except Exception as error:
                logging.getLogger("assistant.runtime").error(
                    "Arrêt incomplet : %s", type(error).__name__
                )
        memoire._MAGASIN = None
        self.capabilities.remove_owner("runtime")
        self.started = False

    def health(self):
        modules = self.modules.health() if self.modules else {}
        return {
            "ok": all(v.get("ok", False) for v in modules.values()),
            "headless": True,
            "tools": len(self.tools.tous()),
            "capabilities": self.capabilities.names(),
            "modules": modules,
        }


runtime = Runtime()
