"""Confirmations courtes : attendre l'accord sans lire un menu de réponses."""
from collections import deque
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
import jarvis14 as red
from core import personnalite, satellite, voix_locales


class ConfirmationCourteTests(unittest.TestCase):
    def test_veille_question_seule_et_accord_explicite(self):
        with patch.object(red, '_MICRO_MUET', threading.Event()), \
                patch.object(red, '_hud'), patch.object(red, 'bip'), \
                patch.object(red, '_dire_en_vidant_micro') as parler, \
                patch.object(red, 'capturer', return_value=np.ones(4000)), \
                patch.object(red, 'transcrire_demande', return_value='oui'):
            self.assertIsNone(red.attendre_apres_reponse(Mock(), deque(), Mock(), Mock(), forcer_confirmation=True))
        self.assertEqual([c.args[0] for c in parler.call_args_list],
                         ['Est-ce que je peux me mettre en veille ?', 'Très bien, je passe en veille.'])

    def test_route_directe_demande_confirmation_sans_liste(self):
        decision = SimpleNamespace(type='outil', outil='test_sensible', arguments={})
        with patch('core.routage_intentions.decider_prioritaire', return_value=decision), \
                patch.object(red.registre, 'get', return_value=Mock()), \
                patch.object(red, '_executer_outils', return_value=[]), \
                patch.object(red.registre, 'annonce_en_attente', return_value="Je vais ouvrir l'application."), \
                patch.object(red, '_hud'), patch.object(red, '_est_interrompu', return_value=False), \
                patch.object(red, 'dire') as parler:
            resultat = red._repondre_route_prioritaire_commune([{'role': 'user', 'content': 'ouvre cette application'}])
        self.assertEqual(resultat, red.SENTINEL_CONFIRM)
        parler.assert_called_once_with("Je vais ouvrir l'application. Tu confirmes ?", interruptible=False)

    def test_outil_demande_par_llm_ne_recite_pas_les_choix(self):
        bloc = SimpleNamespace(type='tool_use', name='test_sensible', input={}, id='test')
        provider = Mock(nom='Ollama')
        provider.repondre.return_value = SimpleNamespace(stop_reason='tool_use', content=[bloc])
        with patch.object(red, '_repondre_route_prioritaire_commune', return_value=None), \
                patch('core.llm.llm', return_value=provider), \
                patch.object(red.registre, 'schemas_api', return_value=[]), \
                patch.object(red, '_executer_outils', return_value=[]), \
                patch.object(red.registre, 'annonce_en_attente', return_value="Je vais ouvrir l'application."), \
                patch.object(red, '_hud'), patch.object(red, '_est_interrompu', return_value=False), \
                patch.object(red, 'dire') as parler:
            resultat = red._repondre_sans_accuse([{'role': 'user', 'content': 'ouvre cette application'}])
        self.assertEqual(resultat, red.SENTINEL_CONFIRM)
        parler.assert_called_once_with("Je vais ouvrir l'application. Tu confirmes ?", interruptible=False)

    def test_satellite_garde_confirmation_pour_n2_et_n3(self):
        decision = SimpleNamespace(type='outil', outil='test_sensible', arguments={})
        for niveau in ('N2', 'N3'):
            with self.subTest(niveau=niveau):
                outil = SimpleNamespace(confirmation=True, annonce=lambda args: 'Je vais agir.')
                session = SimpleNamespace(historique=[], en_attente=None)
                with patch('core.registre.get', return_value=outil), \
                        patch('core.registre.est_autorise', return_value=False), \
                        patch('core.registre.niveau', return_value=niveau), \
                        patch.object(satellite, '_executer_outil') as executer:
                    resultat = satellite._executer_decision_prioritaire(session, decision)
                self.assertEqual(resultat, {'reponse': 'Je vais agir. Tu confirmes ?', 'attente_confirmation': True})
                self.assertEqual(session.en_attente, ('test_sensible', {}))
                executer.assert_not_called()

    def test_accord_et_memorisation_restent_compris_sans_propositions(self):
        for reponse, memoriser in [('oui', False), ('oui toujours', True)]:
            whisper = Mock()
            whisper.transcribe.return_value = ([SimpleNamespace(text=reponse)], None)
            with self.subTest(reponse=reponse), \
                    patch.object(red, 'capturer', return_value=np.ones(4000)), \
                    patch.object(red, '_hud'), patch.object(red, '_dire_en_vidant_micro'), \
                    patch.object(red, '_est_interrompu', return_value=False), \
                    patch.object(red.registre, 'executer_confirme', return_value="C'est fait.") as executer, \
                    patch.object(red.registre, 'annuler_confirme') as annuler:
                red._confirmer(False, False, whisper, [], Mock())
                executer.assert_called_once_with(memoriser=memoriser)
                annuler.assert_not_called()


class IdentiteRedTests(unittest.TestCase):
    def test_nom_red_compatible_avec_personnalite_existante(self):
        from tools.personnalite import changer_personnalite
        with patch('core.config.definir') as definir:
            self.assertEqual(changer_personnalite('red'), 'Mode Red active.')
            definir.assert_called_once_with('assistant.personnalite', 'jarvis_sarcastique')
        self.assertEqual(personnalite.normaliser('jarvis'), personnalite.normaliser('red'))
        self.assertIn('Tu es Red.', personnalite.persona(personnalite.normaliser('red')))

    def test_catalogue_piper_affiche_red_et_garde_l_identifiant(self):
        voix = next(v for v in voix_locales.catalogue() if v['id'] == 'jarvis_fr')
        self.assertEqual(voix['nom'], 'Red — style français')
        self.assertNotIn('Jarvis', voix['description'])


if __name__ == '__main__':
    unittest.main()
