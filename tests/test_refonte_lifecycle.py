import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core import config
from core.capabilities import CapabilityRegistry
from core.evenements import LocalEventBus
from core.module_manager import ModuleManager


class RefonteLifecycleTests(unittest.TestCase):
    def test_extension_runs_without_optional_admin_dependency(self):
        runtime = SimpleNamespace(capabilities=CapabilityRegistry(), events=LocalEventBus())
        runtime.capabilities.publish('events.local', runtime.events, 'runtime')
        manager = ModuleManager(runtime, Path(__file__).resolve().parents[1] / 'modules',
                                {'demo': {'enabled': True}})
        try:
            with patch.dict('sys.modules', {'fastapi': None}):
                manager.start()
                self.assertTrue(manager.health()['demo']['ok'])
                self.assertEqual(runtime.capabilities.require('demo.ping')(), 'pong')
        finally:
            manager.stop()

    def test_extension_can_declare_n3_without_editing_central_policy(self):
        from core import registre
        from security import authorization

        name = "test_extension_critical"
        try:
            registre.outil(nom=name, description="Test", permission_level="N3")(
                lambda: "ok"
            )
            self.assertTrue(registre.get(name).confirmation)
            self.assertEqual(authorization.niveau(name), "N3")
            self.assertTrue(authorization.est_n3(name))
            self.assertFalse(authorization.autoriser_toujours(name))
        finally:
            registre.retirer(name, registre.get(name))

    def test_invalid_module_security_metadata_is_rejected(self):
        from core import registre

        with self.assertRaises(ValueError):
            registre.outil(nom="invalid", description="", permission_level="N0")
        self.assertIsNone(registre.get("invalid"))

    def test_bad_yaml_sections_are_reported_before_migration(self):
        for section in ("tts", "piper", "assistant", "admin"):
            with self.subTest(section=section), self.assertRaises(ValueError):
                config.migrate({section: []})

    def test_module_endpoint_is_revoked_on_stop(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        runtime = SimpleNamespace(
            capabilities=CapabilityRegistry(), events=LocalEventBus()
        )
        runtime.capabilities.publish("events.local", runtime.events, "runtime")
        manager = ModuleManager(
            runtime,
            Path(__file__).resolve().parents[1] / "modules",
            {"demo": {"enabled": True}},
        )
        manager.start()
        try:
            app = FastAPI()
            for path, endpoint, methods in manager.records["demo"].api.admin_routes:
                app.add_api_route(path, endpoint, methods=list(methods))
            with TestClient(app) as client:
                self.assertEqual(
                    client.get("/api/panneau/modules/demo/health").status_code, 200
                )
                manager.stop()
                self.assertEqual(
                    client.get("/api/panneau/modules/demo/health").status_code, 503
                )
        finally:
            manager.stop()

    def test_device_capability_reads_latest_catalogue(self):
        from assistant_vocal.runtime import _DeviceAccess

        runtime = SimpleNamespace(devices=SimpleNamespace(value="before"))
        capability = _DeviceAccess(runtime)
        runtime.devices = SimpleNamespace(value="after")
        self.assertEqual(capability.value, "after")

    def test_installer_preserves_configuration(self):
        from scripts import preparer_red
        import yaml

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = {
                "mode": "local",
                "tts": {"moteur": "chatterbox", "profil": "reddington"},
                "hue": {"cle": "test-secret"},
                "audio": {"micro": "Mon casque"},
            }
            file = root / "config.yaml"
            file.write_text(yaml.safe_dump(original), encoding="utf8")
            with patch.object(preparer_red, "RACINE", root), patch.object(
                config, "FICHIER", file
            ), patch.object(config, "_CONFIG", None):
                preparer_red.configurer()
                first = file.read_bytes()
                preparer_red.configurer()
                self.assertEqual(file.read_bytes(), first)
                result = yaml.safe_load(first)
                self.assertEqual(result["tts"]["profile"], "reddington")
                self.assertEqual(result["hue"], original["hue"])
                self.assertEqual(result["audio"], original["audio"])
