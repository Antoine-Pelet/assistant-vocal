"""Régressions de capture, veille explicite et accusé pendant le calcul."""
from collections import deque
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import numpy as np
from core.conversation_audio import capturer_phrase, intention_veille
from core.instance import InstanceUnique
from core import panneau
import jarvis14 as red


def bloc(niveau=0.0):
    return np.full(1280, niveau, dtype=np.float32)


class CaptureTests(unittest.TestCase):
    def test_silence_non_transcrit(self):
        lire = Mock(return_value=bloc())
        self.assertIsNone(capturer_phrase(lire, deque()))
        self.assertEqual(lire.call_count, 50)  # 4 s d'audio, sans attendre 4 s de CPU

    def test_commence_apres_plus_de_une_seconde_et_garde_les_pauses(self):
        frames = [bloc()] * 30 + [bloc(.1)] * 6 + [bloc()] * 12 + [bloc(-.1)] * 6 + [bloc()] * 20
        audio = capturer_phrase(Mock(side_effect=frames), deque())
        self.assertIsNotNone(audio)
        self.assertTrue(np.any(audio == .1))
        self.assertTrue(np.any(audio == -.1))
        self.assertLess(len(audio), sum(map(len, frames)))

    def test_prebuffer_conserve_debut_et_reponse_courte(self):
        tampon = deque([bloc(), bloc(.2), bloc(.2)])
        audio = capturer_phrase(Mock(return_value=bloc()), tampon, duree_min=.2)
        self.assertTrue(np.any(audio == .2))
        self.assertFalse(tampon)

    def test_impulsion_unique_rejetee(self):
        lire = Mock(side_effect=[bloc(.2)] + [bloc()] * 20)
        self.assertIsNone(capturer_phrase(lire, deque()))

    def test_limite_mesuree_en_audio_meme_si_les_blocs_sont_deja_en_file(self):
        lire = Mock(return_value=bloc(.1))
        audio = capturer_phrase(lire, deque(), duree_max=2)
        self.assertEqual(lire.call_count, 25)
        self.assertEqual(len(audio), 32000)


class IntentionTests(unittest.TestCase):
    def test_confirmation_expresse_sans_faux_oui(self):
        for t in ('oui', 'Oui, tu peux.', 'mets-toi en veille', 'Bonne nuit'):
            self.assertEqual(intention_veille(t), 'veille')
        for t in ('non', 'pas encore', 'ne te mets pas en veille'):
            self.assertEqual(intention_veille(t), 'continuer')
        for t in ('ouvre YouTube', 'oui mais ouvre le panneau', 'recherche le mot ouistiti'):
            self.assertEqual(intention_veille(t), 'commande')
        for t in ('', 'peut-être'):
            self.assertEqual(intention_veille(t), 'incertain')


class VeilleTests(unittest.TestCase):
    def setUp(self):
        self.flux, self.whisper, self.reveil = Mock(), Mock(), Mock()
        self.tampon = deque()
        self.patches = [patch.object(red, '_MICRO_MUET', threading.Event()),
                        patch.object(red, '_hud'), patch.object(red, 'bip'),
                        patch.object(red, '_dire_en_vidant_micro'),
                        patch.object(red.config, 'reglage', side_effect=lambda k, d=None: d)]
        self.mocks = [p.start() for p in self.patches]
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])

    def attendre(self):
        return red.attendre_apres_reponse(self.flux, self.tampon, self.whisper, self.reveil)

    def test_oui_retourne_veille(self):
        with patch.object(red, 'attendre_suite', return_value=False), \
                patch.object(red, 'capturer', return_value=bloc(.1)), \
                patch.object(red, 'transcrire_demande', return_value='oui'):
            self.assertIsNone(self.attendre())
        self.assertIn('passe en veille', self.mocks[3].call_args.args[0])

    def test_silence_ne_confirme_pas_et_ne_repete_pas_la_question(self):
        with patch.object(red, 'attendre_suite', side_effect=[False, True]), \
                patch.object(red, 'capturer', side_effect=[None, bloc(.1)]), \
                patch.object(red, 'transcrire_demande', return_value='oui') as stt:
            self.assertIsNone(self.attendre())
        stt.assert_called_once()
        questions = [c for c in self.mocks[3].call_args_list if 'Est-ce que' in c.args[0]]
        self.assertEqual(len(questions), 1)

    def test_non_puis_demande_conserve_la_transcription(self):
        audio = bloc(.1)
        with patch.object(red, 'attendre_suite', side_effect=[False, True]), \
                patch.object(red, 'capturer', return_value=audio), \
                patch.object(red, 'transcrire_demande', side_effect=['non', 'ouvre le panneau']):
            retour, texte = self.attendre()
        self.assertIs(retour, audio)
        self.assertEqual(texte, 'ouvre le panneau')

    def test_nouvelle_demande_immediate_ne_pose_pas_la_question(self):
        audio = bloc(.1)
        with patch.object(red, 'attendre_suite', return_value=True), \
                patch.object(red, 'capturer', return_value=audio):
            retour, texte = self.attendre()
        self.assertIs(retour, audio)
        self.assertIsNone(texte)
        self.mocks[3].assert_not_called()

    def test_mute_reste_prioritaire(self):
        red._MICRO_MUET.set()
        with patch.object(red, 'attendre_suite', return_value=False):
            self.assertIsNone(self.attendre())
        self.mocks[3].assert_not_called()


class AccuseTests(unittest.TestCase):
    def test_accuse_et_calcul_paralleles_mais_parole_serialisee(self):
        debut_accuse = threading.Event()
        calcul = threading.Event()
        termine = threading.Event()
        def parler(texte):
            if texte == 'réponse finale':
                self.assertTrue(termine.is_set())
            else:
                debut_accuse.set()
                self.assertTrue(calcul.wait(2))
                termine.set()
        def repondre(_):
            self.assertTrue(debut_accuse.wait(2))
            calcul.set()
            red.dire('réponse finale')
            return 'réponse finale'
        with patch.object(red.config, 'reglage', return_value=True), \
                patch.object(red, '_hud'), patch.object(red, '_dire', side_effect=lambda t, i: parler(t)), \
                patch.object(red, '_repondre_sans_accuse', side_effect=repondre):
            self.assertEqual(red.repondre([]), 'réponse finale')
        self.assertTrue(termine.is_set())

    def test_accuse_desactivable(self):
        with patch.object(red.config, 'reglage', return_value=False), \
                patch.object(red, 'dire') as parler, \
                patch.object(red, '_repondre_sans_accuse', return_value='ok'):
            self.assertEqual(red.repondre([]), 'ok')
        parler.assert_not_called()


class ReglagesConversationTests(unittest.TestCase):
    def test_delais_bornes_et_booleens(self):
        with patch('core.config.definir') as ecrire:
            for cle, valeur in [('assistant.confirmer_veille', 'true'), ('assistant.accuse_reception', False),
                                ('assistant.silence_fin', 1.6), ('assistant.attente_debut', 4)]:
                self.assertTrue(panneau._definir_reglage(cle, valeur)['ok'])
            ecrire.assert_any_call('assistant.confirmer_veille', True)
            ecrire.reset_mock()
            for cle, valeur in [('assistant.silence_fin', 0), ('assistant.attente_debut', 20),
                                ('assistant.confirmer_veille', 'peut-être'), ([], 2)]:
                self.assertFalse(panneau._definir_reglage(cle, valeur)['ok'])
            ecrire.assert_not_called()


class InstanceTests(unittest.TestCase):
    def test_deuxieme_lancement_bloque_puis_verrou_libere(self):
        with tempfile.TemporaryDirectory() as tmp:
            chemin = Path(tmp) / 'red.lock'
            with InstanceUnique(chemin) as premiere:
                self.assertTrue(premiere)
                with InstanceUnique(chemin) as deuxieme:
                    self.assertFalse(deuxieme)
            with InstanceUnique(chemin) as suivante:
                self.assertTrue(suivante)
