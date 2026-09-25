import json
import threading
import unittest
from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock, patch
import numpy as np

from core.commandes_vocales import commande_assistant, demande_fonctionnalites
from core.interruption_vocale import DetecteurInterruption
from core.routage_intentions import decider_prioritaire
import jarvis14 as red


class CommandesTests(unittest.TestCase):
    def test_questions_naturelles_sur_les_fonctions(self):
        for phrase in ('quelle sont les fonctionnalité actuelle',
                       'Quelles sont les fonctionnalités actuelles ?',
                       'Red, peux-tu me dire quelles sont tes fonctionnalités ?',
                       'Donne-moi tes capacités disponibles s’il te plaît',
                       'J’aimerais connaître les fonctionnalités de Red',
                       'Dis-moi ce que tu sais faire', 'Que peux-tu faire actuellement ?',
                       'Red fonction'):
            with self.subTest(phrase=phrase):
                self.assertTrue(demande_fonctionnalites(phrase))
                self.assertEqual(decider_prioritaire(phrase).outil, 'fonctions_red')

    def test_pas_de_reponse_hors_sujet(self):
        for phrase in ('Explique cette fonction Python', 'Quelles sont les fonctionnalités de Python',
                       'ne me liste pas tes fonctionnalités', 'Quelle est la fonction du cœur ?'):
            self.assertFalse(demande_fonctionnalites(phrase), phrase)

    def test_commandes_locales_avec_politesse_et_faute_courante(self):
        for p in ('Mets-toi en veille', 'mes toi en veille', 'Mettoy en veille.', 'Mette-toi en veille.', 'Red, mets-toi en veille s’il te plaît',
                  'Peux-tu passer en veille', 'Je voudrais que tu te mettes en veille'):
            # « passer » est une formulation infinitive après peux-tu.
            attendu = 'veille'
            self.assertEqual(commande_assistant(p), attendu, p)
        for p in ('arrête Red', 'Arrête de Red.', 'Red, arrête l’assistant', 'Ferme Red s’il te plaît', 'quitte'):
            self.assertEqual(commande_assistant(p), 'quitter', p)
        for p in ('stop', 'Red stop', 'arrête de parler', 'Arrête, arrête.', 'tais-toi', 'coupe ta voix'):
            self.assertEqual(commande_assistant(p), 'silence', p)

    def test_pas_d_arret_pc_ni_de_negation_confondue(self):
        for p in ('arrête le PC', 'mets le PC en veille', 'ne te mets pas en veille',
                  'n’arrête pas Red', 'explique comment arrêter Red', 'cherche un panneau stop'):
            self.assertIsNone(commande_assistant(p), p)


class InterruptionTests(unittest.TestCase):
    def detecteur(self, textes):
        d = DetecteurInterruption.__new__(DetecteurInterruption)
        d.mot = 'red'
        d.reconnaissance = Mock()
        d.reconnaissance.AcceptWaveform.return_value = False
        d.reconnaissance.PartialResult.side_effect = [json.dumps({'partial': t}) for t in textes]
        d.reset()
        return d

    def test_stop_court_sans_quatre_cent_ms_de_parole(self):
        d = self.detecteur(['stop', 'stop'])
        pcm = np.full(1280, 2000, dtype=np.int16)
        self.assertIsNone(d.analyser(pcm, 'Voici le résultat.'))
        self.assertEqual(d.analyser(pcm, 'Voici le résultat.'), 'stop')

    def test_echo_et_silence_rejetes(self):
        for parle, amplitude in [('Tu peux dire stop.', 2000), ('Voici le résultat.', 0)]:
            d = self.detecteur(['stop', 'stop'])
            pcm = np.full(1280, amplitude, dtype=np.int16)
            self.assertIsNone(d.analyser(pcm, parle))
            self.assertIsNone(d.analyser(pcm, parle))

    def test_texte_ordinaire_ne_coupe_pas(self):
        d = self.detecteur(['bonjour', 'bonjour'])
        for _ in range(2):
            self.assertIsNone(d.analyser(np.full(1280, 2000, dtype=np.int16)))


class DialogueLocalTests(unittest.TestCase):
    def setUp(self):
        self.audio = np.ones(16000, dtype=np.float32) * .1
        self.flux, self.whisper, self.reveil = Mock(), Mock(), Mock()
        self.patches = [patch.object(red, '_hud'), patch.object(red, 'dire'),
                        patch.object(red, '_dire_en_vidant_micro'), patch.object(red, 'couper_parole')]
        for p in self.patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])

    def test_veille_ne_passe_pas_par_le_modele(self):
        with patch.object(red, 'repondre_en_ecoutant') as llm:
            issue = red.traiter(self.audio, self.whisper, [], self.flux, self.reveil,
                               question='mes toi en veille')
        self.assertEqual(issue, red.SENTINEL_VEILLE)
        llm.assert_not_called()

    def test_arreter_red_termine_uniquement_la_boucle_assistant(self):
        with patch.object(red, 'repondre_en_ecoutant') as llm:
            with self.assertRaises(red.ArretAssistant):
                red.traiter(self.audio, self.whisper, [], self.flux, self.reveil,
                            question='arrête Red')
        llm.assert_not_called()
        red._dire_en_vidant_micro.assert_called_once()

    def test_veille_explicite_confirmee_meme_si_veille_automatique_desactivee(self):
        with patch.object(red.config, 'reglage', side_effect=lambda k, d=None: False if k == 'assistant.confirmer_veille' else d), \
                patch.object(red, '_MICRO_MUET', threading.Event()), \
                patch.object(red, 'attendre_suite') as suite, patch.object(red, 'bip'), \
                patch.object(red, 'capturer', return_value=self.audio), \
                patch.object(red, 'transcrire_demande', return_value='oui'):
            self.assertIsNone(red.attendre_apres_reponse(self.flux, deque(), self.whisper, self.reveil,
                                                       forcer_confirmation=True))
        suite.assert_not_called()
        self.assertIn('Est-ce que', red._dire_en_vidant_micro.call_args_list[0].args[0])

    def test_arret_possible_pendant_confirmation_veille(self):
        with patch.object(red.config, 'reglage', side_effect=lambda k, d=None: d), \
                patch.object(red, '_MICRO_MUET', threading.Event()), patch.object(red, 'bip'), \
                patch.object(red, 'attendre_suite', return_value=False), \
                patch.object(red, 'capturer', return_value=self.audio), \
                patch.object(red, 'transcrire_demande', return_value='arrête Red'):
            with self.assertRaises(red.ArretAssistant):
                red.attendre_apres_reponse(self.flux, deque(), self.whisper, self.reveil)

    def test_interruption_ne_repond_pas_c_est_fait(self):
        with patch.object(red, 'repondre_en_ecoutant', return_value=('', True, True)):
            self.assertTrue(red.traiter(self.audio, self.whisper, [], self.flux, self.reveil,
                                       question='explique les planètes'))
        red.dire.assert_not_called()


class AnnulationTests(unittest.TestCase):
    def test_ancien_tour_reste_annule_apres_nouvelle_demande(self):
        evenement = threading.Event()
        evenement.set()
        red._CONTEXTE_REPONSE.annulation = evenement
        self.addCleanup(lambda: setattr(red._CONTEXTE_REPONSE, 'annulation', None))
        with patch.object(red, '_INTERRUPTION', threading.Event()), \
                patch.object(red.registre, 'get') as trouver, patch('core.tts.tts') as voix:
            self.assertTrue(red._est_interrompu())
            self.assertEqual(red._executer_outils([SimpleNamespace(type='tool_use', name='test')]), [])
            red._dire('une réponse ancienne')
        trouver.assert_not_called()
        voix.assert_not_called()
