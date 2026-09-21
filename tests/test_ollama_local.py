"""Le démarrage doit vérifier la présence exacte du modèle local demandé."""
import unittest
from unittest.mock import patch

from core.llm import OllamaProvider


class OllamaAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.provider = OllamaProvider()
        self.provider.modele = "qwen3.5:2b"

    @patch("requests.get", create=True)
    def test_autre_taille_ne_suffit_pas(self, get):
        get.return_value.json.return_value = {"models": [{"name": "qwen3.5:4b"}]}
        self.assertFalse(self.provider.disponible())

    @patch("requests.get", create=True)
    def test_modele_exact_present(self, get):
        get.return_value.json.return_value = {"models": [{"name": "qwen3.5:2b"}]}
        self.assertTrue(self.provider.disponible())

    @patch("requests.get", create=True)
    def test_erreur_http_signale_indisponible(self, get):
        get.return_value.raise_for_status.side_effect = RuntimeError("HTTP 500")
        self.assertFalse(self.provider.disponible())

    @patch("requests.get", create=True)
    def test_latest_implicite(self, get):
        self.provider.modele = "qwen3.5"
        get.return_value.json.return_value = {"models": [{"name": "qwen3.5:latest"}]}
        self.assertTrue(self.provider.disponible())

