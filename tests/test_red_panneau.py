"""Contrats de configuration et de préécoute hors ligne, sans modifier config.yaml."""
import io
import unittest
import wave
from unittest.mock import Mock, patch

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core import panneau, voix_locales


class ReglagesRedTests(unittest.TestCase):
    def test_jarvis_active_piper_et_reinitialise_la_voix(self):
        with patch('core.config.definir') as ecrire, \
                patch.object(voix_locales, 'installee', return_value=True), \
                patch('core.tts.reinitialiser') as reset:
            self.assertTrue(panneau._definir_reglage('tts.voix_locale', 'jarvis_fr')['ok'])
        ecrire.assert_any_call('tts.voix_locale', 'jarvis_fr')
        ecrire.assert_any_call('piper.modele', 'voix/fr_FR-tom-medium.onnx')
        ecrire.assert_any_call('tts.moteur', 'piper')
        reset.assert_called_once()

    def test_refus_sans_ecriture(self):
        with patch('core.config.definir') as ecrire:
            for cle, valeur in [('tts.voix_locale', '../../autre'), ('assistant.stabilite_reveil', 0),
                                ('assistant.stabilite_reveil', 2.5), ('assistant.stabilite_reveil', True),
                                ('assistant.duree_suite', 31), ('assistant.seuil_reveil', float('nan'))]:
                with self.subTest(cle=cle, valeur=valeur):
                    self.assertFalse(panneau._definir_reglage(cle, valeur)['ok'])
            with patch.object(voix_locales, 'installee', return_value=False):
                self.assertFalse(panneau._definir_reglage('tts.voix_locale', 'jarvis_fr')['ok'])
        ecrire.assert_not_called()

    def test_micro_persiste_un_nom_stable_et_retablit_frequence_auto(self):
        micro = {'index': 7, 'valeur': 'Casque USB, Windows WASAPI'}
        with patch.object(panneau, '_audio_devices', return_value=([micro], [])), \
                patch('core.config.definir') as ecrire:
            resultat = panneau._definir_reglage('audio.micro', 7)
            self.assertTrue(resultat['redemarrage'])
            ecrire.assert_any_call('audio.micro', micro['valeur'])
            ecrire.assert_any_call('audio.taux', None)
            ecrire.reset_mock()
            self.assertFalse(panneau._definir_reglage('audio.micro', 'absent')['ok'])
            ecrire.assert_not_called()

    def test_effet_audio_sans_ecretage_ni_mutation(self):
        audio = np.tile(np.array([32767, -32768, 0], dtype=np.int16), 1000)
        original = audio.copy()
        sortie, taux = voix_locales.appliquer_effet(audio, 44100, 'jarvis_fr')
        self.assertEqual(sortie.dtype, np.int16)
        self.assertEqual(len(sortie), len(audio))
        self.assertTrue(40000 < taux < 44100)
        np.testing.assert_array_equal(audio, original)
        naturel, taux = voix_locales.appliquer_effet(audio, 44100, 'tom_fr')
        self.assertIs(naturel, audio)
        self.assertEqual(taux, 44100)


class ApiRedTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        panneau.monter_routes(self.app)
        self.client = TestClient(self.app, client=('127.0.0.1', 45000))

    def test_panneau_protege_des_clients_distants_et_formulaires(self):
        distant = TestClient(self.app, client=('192.168.1.12', 45000))
        self.assertEqual(distant.get('/api/panneau/fonctionnalites').status_code, 403)
        self.assertEqual(self.client.get('/panneau', headers={'X-Forwarded-For': '1.2.3.4'}).status_code, 403)
        self.assertEqual(self.client.post('/api/panneau/voix/apercu', content='id=jarvis_fr').status_code, 415)

    def test_apercu_wav_sans_changer_la_configuration(self):
        voix = Mock(synthetiser=Mock(return_value=(np.zeros(800, dtype=np.int16), 16000)))
        with patch('core.tts.PiperProvider', return_value=voix) as provider, \
                patch.object(voix_locales, 'installee', return_value=True), \
                patch('core.config.definir') as ecrire:
            reponse = self.client.post('/api/panneau/voix/apercu', json={'id': 'jarvis_fr'})
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.headers['content-type'], 'audio/wav')
        with wave.open(io.BytesIO(reponse.content)) as wav:
            self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (1, 2, 16000))
        provider.assert_called_once_with(profil='jarvis_fr')
        ecrire.assert_not_called()

    def test_demandes_invalides_ne_lancent_pas_le_moteur(self):
        with patch('core.tts.PiperProvider') as provider:
            for donnees in ([], {'id': '../test'}, {'id': ['jarvis_fr']}):
                self.assertEqual(self.client.post('/api/panneau/voix/apercu', json=donnees).status_code, 400)
            self.assertEqual(self.client.post('/api/panneau/reglage', json=[]).status_code, 200)
            self.assertFalse(self.client.post('/api/panneau/reglage', json=[]) .json()['ok'])
        provider.assert_not_called()
