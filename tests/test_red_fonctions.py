"""Commandes directes et catalogue honnête, sans modèle ni intégration distante."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core import fonctionnalites
from core.routage_intentions import decider_prioritaire


class FonctionsTests(unittest.TestCase):
    @patch('core.reveil.mot_activation', return_value='red')
    def test_aide_et_panneau_avant_tout_llm(self, _):
        for phrase in ('red fonction', 'Red, fonctionnalités !', 'fonctions', 'Que peux-tu faire ?'):
            with self.subTest(phrase=phrase):
                self.assertEqual(decider_prioritaire(phrase).outil, 'fonctions_red')
        for phrase in ('red panneau', '/panneau', 'ouvre le panneau de configuration'):
            self.assertEqual(decider_prioritaire(phrase).outil, 'ouvrir_panneau')

    def test_ne_capture_pas_une_question_sur_une_fonction(self):
        for phrase in ('explique cette fonction Python', 'comment fonctionne le micro', 'redémarre', ''):
            self.assertFalse(fonctionnalites.demande_fonctions(phrase))

    def etat(self, dialogue):
        outils = [SimpleNamespace(nom=n) for n in ('noter', 'notes_du_jour', 'chercher_web', 'allumer_lumiere')]
        def lire(cle, defaut=None):
            return 'local' if cle == 'mode' else defaut
        with patch.object(fonctionnalites.registre, 'tous', return_value=outils), \
                patch.object(fonctionnalites.config, 'reglage', side_effect=lire), \
                patch('core.llm.llm', return_value=Mock(disponible=Mock(return_value=dialogue))):
            return fonctionnalites.catalogue()

    def test_configuration_et_outils_charges_sont_pris_en_compte(self):
        etat = self.etat(True)
        groupes = {f['id']: f['statut'] for f in etat['fonctions']}
        self.assertEqual(groupes['notes'], 'disponible')
        self.assertEqual(groupes['web'], 'a_configurer')
        self.assertEqual(groupes['hue'], 'a_configurer')
        self.assertEqual(groupes['stats'], 'indisponible')
        self.assertEqual(etat['disponibles'], sum(v == 'disponible' for v in groupes.values()))

    def test_ollama_arrete_aide_reste_disponible(self):
        etat = self.etat(False)
        groupes = {f['id']: f['statut'] for f in etat['fonctions']}
        self.assertEqual(groupes['aide'], 'disponible')
        self.assertEqual(groupes['notes'], 'indisponible')
        with patch.object(fonctionnalites, 'catalogue', return_value=etat):
            texte = fonctionnalites.resume_vocal()
        self.assertIn('mes fonctions et mes réglages', texte)
        self.assertNotIn('notes et idées', texte)
        self.assertIn('Red panneau', texte)
