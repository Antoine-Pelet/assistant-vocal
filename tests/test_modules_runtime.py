"""Un module s'ajoute sans modification spécifique d'un composant central."""

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from core.capabilities import CapabilityRegistry
from core.evenements import LocalEventBus, Event
from core.module_manager import ModuleManager
from core import registre


class ExtensionTests(unittest.TestCase):
    def make(self, enabled=True):
        r = SimpleNamespace(capabilities=CapabilityRegistry(), events=LocalEventBus())
        r.capabilities.publish("events.local", r.events, "runtime")
        return r, ModuleManager(
            r,
            Path(__file__).resolve().parents[1] / "modules",
            {"demo": {"enabled": enabled, "message": "bonjour"}},
        )

    def test_disabled_does_not_import_code(self):
        r, m = self.make(False)
        with patch("core.module_manager.importlib.import_module") as importer:
            m.start()
        importer.assert_not_called()
        self.assertIsNone(registre.get("demo_ping"))
        self.assertEqual(m.records["demo"].state, "DISCOVERED")

    def test_complete_lifecycle_and_cleanup(self):
        r, m = self.make()
        try:
            m.start()
            m.start()
            self.assertEqual(registre.get("demo_ping").fonction(), "bonjour")
            self.assertEqual(r.capabilities.require("demo.ping")(), "bonjour")
            r.events.publish(Event.create("demo.request", {}))
            self.assertEqual(m.health()["demo"]["events_received"], 1)
            self.assertEqual(len(m.records["demo"].api.admin_routes), 1)
        finally:
            m.stop()
        self.assertIsNone(registre.get("demo_ping"))
        self.assertIsNone(r.capabilities.get("demo.ping"))
        r.events.publish(Event.create("demo.request", {}))
        self.assertEqual(m.records["demo"].instance.events, 1)

    def test_missing_capability_does_not_import_module(self):
        r, m = self.make()
        r.capabilities.remove_owner("runtime")
        with patch("core.module_manager.importlib.import_module") as importer:
            m.start()
        importer.assert_not_called()
        self.assertFalse(m.health()["demo"]["ok"])

    def test_stop_then_start_registers_once(self):
        r, m = self.make()
        try:
            m.start()
            m.stop()
            m.start()
            r.events.publish(Event.create("demo.request", {}))
            self.assertEqual(m.health()["demo"]["events_received"], 1)
        finally:
            m.stop()

    def test_capability_cannot_be_overwritten(self):
        r, m = self.make()
        with self.assertRaises(ValueError):
            r.capabilities.publish("events.local", object(), "other")
        r.capabilities.remove_owner("other")
        self.assertIs(r.capabilities.require("events.local"), r.events)
