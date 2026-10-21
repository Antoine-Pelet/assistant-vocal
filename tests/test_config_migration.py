import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml
from core import config


class ConfigurationTests(unittest.TestCase):
    def test_migration_is_idempotent_and_keeps_unrelated_secrets(self):
        old = {
            "tts": {
                "moteur": "chatterbox",
                "profil": "reddington",
                "voix_locale": "jarvis_fr",
            },
            "assistant": {"nom": "Red", "personnalite": "jarvis_sarcastique"},
            "hue": {"cle": "secret-test"},
        }
        saved = copy.deepcopy(old)
        new = config.validate(config.migrate(old))
        self.assertEqual(old, saved)
        self.assertEqual(config.migrate(new), new)
        self.assertEqual(new["tts"]["profile"], "reddington")
        self.assertEqual(new["piper"]["profile"], "tom_fr")
        self.assertEqual(new["hue"], old["hue"])
        self.assertNotIn("moteur", new["tts"])

    def test_failed_replace_keeps_file_and_memory_configuration(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "config.yaml"
            file.write_text("mode: local\n", encoding="utf8")
            with patch.object(config, "FICHIER", file), patch.object(
                config, "_CONFIG", None
            ):
                before = copy.deepcopy(config._charger())
                with patch("core.config.os.replace", side_effect=OSError("test")):
                    with self.assertRaises(OSError):
                        config.definir("assistant.name", "Autre")
                self.assertEqual(config._CONFIG, before)
                self.assertEqual(file.read_text(), "mode: local\n")
                self.assertEqual(list(Path(temp).glob("*.tmp")), [])

    def test_invalid_data_never_written(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "config.yaml"
            with patch.object(config, "FICHIER", file), patch.object(
                config, "_CONFIG", None
            ):
                with self.assertRaises(ValueError):
                    config.definir("tts.engine", "absent")
                self.assertFalse(file.exists())
                config.definir("assistant.nom", "Red")
                data = yaml.safe_load(file.read_text(encoding="utf8"))
                self.assertEqual(data["assistant"]["name"], "Red")
                self.assertNotIn("nom", data["assistant"])
