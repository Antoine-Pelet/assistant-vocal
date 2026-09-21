"""Contrat de détection de Red, sans micro ni modèle téléchargé."""
import json
import re
import unittest
from collections import deque
from unittest.mock import Mock, patch

from core.reveil import ReveilVosk, retirer_activation, charger_reveil


class WakeTests(unittest.TestCase):
    @patch("core.reveil.mot_activation", return_value="red")
    def test_prefixe_uniquement(self, _):
        for texte in ("Red, ouvre YouTube", "RED : ouvre YouTube", "red ouvre YouTube",
                      "Hey red ! ouvre YouTube"):
            self.assertEqual(retirer_activation(texte), "ouvre YouTube")
        for texte in ("redémarre le PC", "redessine le logo", "parle de Red", "fred ouvre"):
            self.assertEqual(retirer_activation(texte), texte)
        self.assertEqual(retirer_activation("Red !"), "")

    def detecteur(self, textes, final=False):
        reveil = ReveilVosk.__new__(ReveilVosk)
        reveil.mot = "red"
        reveil.stabilite = 3
        reveil._expression = re.compile(r"\bred\b", re.I)
        reveil._consecutifs = 0
        reveil._declenche = False
        reveil._audio = deque(maxlen=38)
        reveil._verifier = None
        reveil._attente_verif = 0
        reveil._reconnaissance = Mock()
        reveil._reconnaissance.AcceptWaveform.return_value = final
        resultats = [json.dumps({"text" if final else "partial": t}) for t in textes]
        methode = reveil._reconnaissance.Result if final else reveil._reconnaissance.PartialResult
        methode.side_effect = resultats
        return reveil

    def test_hypothese_instable_ne_declenche_pas(self):
        d = self.detecteur(["red", "", "bonjour", "redessine", "hey jarvis"])
        self.assertEqual([d.predict(Mock())["red"] for _ in range(5)], [0] * 5)

    def test_hypothese_stable_declenche_une_fois(self):
        d = self.detecteur(["red", "red", "red", "red"])
        self.assertEqual([d.predict(Mock())["red"] for _ in range(4)], [0, 0, 1, 0])
        d.reset()
        d._reconnaissance.Reset.assert_called_once()
        self.assertFalse(d._declenche)
        self.assertEqual(d._consecutifs, 0)

    def test_resultat_final_accepte(self):
        d = self.detecteur(["red"], final=True)
        self.assertEqual(d.predict(Mock()), {"red": 1.0})

    def test_confirmation_rejette_un_faux_positif(self):
        import numpy as np
        d = self.detecteur(["red"], final=True)
        d._verifier = Mock(return_value=False)
        self.assertEqual(d.predict(np.zeros(1280, dtype=np.int16)), {"red": 0.0})
        d._verifier.assert_called_once()

    @patch("core.reveil.config.reglage", return_value="inconnu")
    def test_moteur_inconnu_refuse(self, _):
        with self.assertRaisesRegex(ValueError, "Moteur"):
            charger_reveil()


if __name__ == "__main__":
    unittest.main()
