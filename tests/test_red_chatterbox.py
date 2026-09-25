"""Contrats du moteur local, configuration et protocole sans poids ni GPU."""
import base64
from contextlib import nullcontext
import json
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
from core import chatterbox_tts as cb, config, tts, routage
from scripts.chatterbox_worker import Moteur, morceaux


class ProfilsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'voices').mkdir()
        (self.root / 'voices/jarvis.wav').write_bytes(b'reference')
        (self.root / 'voices/reddington.wav').write_bytes(b'reference2')
        self.conf = {'mode': 'local', 'tts': {'moteur': 'chatterbox', 'profil': 'jarvis'},
                     'voices': {'jarvis': {'reference': 'voices/jarvis.wav', 'exaggeration': .2, 'cfg_weight': .45},
                                'reddington': {'reference': 'voices/reddington.wav', 'exaggeration': .4, 'cfg_weight': .35}}}
        self.patch_config = patch.object(config, '_CONFIG', self.conf)
        self.patch_config.start()
        self.addCleanup(self.patch_config.stop)
        self.patch_root = patch.object(cb, 'RACINE', self.root)
        self.patch_root.start()
        self.addCleanup(self.patch_root.stop)

    def test_chemins_depuis_projet_et_selection_sans_code(self):
        jarvis = cb.configuration()
        self.assertEqual(jarvis['reference'], str((self.root / 'voices/jarvis.wav').resolve()))
        self.assertEqual((jarvis['exaggeration'], jarvis['cfg_weight']), (.2, .45))
        self.conf['tts']['profil'] = 'reddington'
        reddington = cb.configuration()
        self.assertTrue(reddington['reference'].endswith('reddington.wav'))
        self.assertEqual((reddington['exaggeration'], reddington['cfg_weight']), (.4, .35))

    def test_valeurs_invalides_refusees(self):
        for cle, valeur in [('exaggeration', float('nan')), ('cfg_weight', float('inf')),
                            ('cfg_weight', -1), ('cfg_weight', 1.1), ('exaggeration', True),
                            ('temperature', 0), ('reference', 'https://exemple.fr/voix.wav'),
                            ('reference', '//serveur/voix.wav'), ('reference', 'voices/absent.wav')]:
            with self.subTest(cle=cle, valeur=valeur), patch.dict(self.conf['voices']['jarvis'], {cle: valeur}):
                with self.assertRaises((ValueError, TypeError)):
                    cb.configuration()
        with self.assertRaises(ValueError):
            cb.configuration('absent')

    def test_absence_wav_ne_demarre_pas_worker_et_repli_local(self):
        self.conf['voices']['jarvis']['reference'] = 'voices/absent.wav'
        provider = cb.ChatterboxProvider()
        self.addCleanup(provider.fermer)
        attendu = (np.array([1, 2], dtype=np.int16), 22050)
        with patch.object(provider, '_demarrer') as demarrer, \
                patch('core.tts.PiperProvider') as piper:
            piper.return_value.synthetiser.return_value = attendu
            self.assertIs(provider.synthetiser('Bonjour'), attendu)
            demarrer.assert_not_called()
            piper.return_value.synthetiser.assert_called_once_with('Bonjour')

    def test_fabrique_et_reinitialisation_ferment_worker(self):
        with patch.object(tts, '_TTS', None):
            provider = tts.tts()
            self.assertIsInstance(provider, cb.ChatterboxProvider)
            with patch.object(provider, 'fermer') as fermer:
                tts.reinitialiser()
                fermer.assert_called_once()

    def test_local_continue_de_refuser_elevenlabs(self):
        self.conf['tts']['moteur'] = 'elevenlabs'
        with patch.object(tts, '_TTS', None):
            self.assertIsInstance(tts.tts(), tts.PiperProvider)

    def test_panneau_refuse_wav_absent_sans_modifier_config(self):
        from core import panneau
        self.conf['voices']['jarvis']['reference'] = 'voices/absent.wav'
        with patch('core.config.definir') as ecrire:
            resultat = panneau._definir_reglage('tts.moteur', 'chatterbox')
            self.assertFalse(resultat['ok'])
            self.assertIn('WAV', resultat['message'])
            ecrire.assert_not_called()

    def test_panneau_accepte_profil_valide_et_reinitialise(self):
        from core import panneau
        with patch.object(cb.ChatterboxProvider, 'verifier', return_value={}), \
                patch('core.config.definir') as ecrire, patch('core.tts.reinitialiser') as reset:
            self.assertTrue(panneau._definir_reglage('tts.profil', 'reddington')['ok'])
            ecrire.assert_called_once_with('tts.profil', 'reddington')
            reset.assert_called_once()

    def test_protocole_reel_processus_persistant_et_hors_ligne(self):
        # Un petit worker de protocole, aucun modèle simulé présenté comme un TTS.
        dossier = self.root / 'scripts'
        dossier.mkdir()
        (dossier / 'chatterbox_worker.py').write_text('''import base64, json, os, sys
for line in sys.stdin:
    data = json.loads(line)
    assert os.environ['HF_HUB_OFFLINE'] == '1'
    assert os.environ['TRANSFORMERS_OFFLINE'] == '1'
    assert data['texte'] == 'Bonjour, Monsieur.'
    print(json.dumps({'ok':True, 'pcm':base64.b64encode(bytes([1,0,255,127])).decode(), 'frequence':24000, 'device':'cpu'}), flush=True)
''', encoding='utf-8')
        provider = cb.ChatterboxProvider()
        self.addCleanup(provider.fermer)
        with patch.object(provider, '_python', return_value=Path(sys.executable)), \
                patch.object(provider, 'verifier', return_value=cb.configuration()):
            audio, freq = provider.generer('Bonjour, Monsieur.')
            premier = provider._processus
            np.testing.assert_array_equal(audio, [1, 32767])
            self.assertEqual(freq, 24000)
            provider.generer('Bonjour, Monsieur.')
            self.assertIs(provider._processus, premier)
            provider.fermer()
            self.assertIsNotNone(premier.poll())

    def test_delai_expire_tue_worker(self):
        provider = cb.ChatterboxProvider()
        provider._processus = Mock()
        provider._reponses = Mock(get=Mock(side_effect=queue.Empty))
        with patch.object(provider, 'verifier', return_value=cb.configuration()), \
                patch.object(provider, '_demarrer'), patch.object(provider, 'fermer') as fermer:
            with self.assertRaises(TimeoutError):
                provider.generer('Bonjour')
            fermer.assert_called_once()


class WorkerTests(unittest.TestCase):
    def test_processus_worker_bloque_reellement_les_connexions(self):
        script = '''import sys, socket
from scripts.chatterbox_worker import interdire_reseau
sys.addaudithook(interdire_reseau)
try:
    socket.getaddrinfo('example.com', 443)
except RuntimeError as exc:
    assert 'hors ligne' in str(exc)
else:
    raise AssertionError('Connexion non bloquée')
'''
        resultat = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True,
                                  cwd=Path(__file__).resolve().parent.parent, timeout=10)
        self.assertEqual(resultat.returncode, 0, resultat.stderr)

    def test_decoupage_conserve_tous_les_mots(self):
        texte = 'Très bien, Monsieur. ' + ('Ceci est une longue réponse française. ' * 50)
        phrases = morceaux(texte)
        self.assertTrue(all(len(p) <= 240 for p in phrases))
        self.assertEqual(' '.join(phrases).split(), texte.split())

    def test_selection_cpu_sans_cuda_et_cache_modele(self):
        moteur = Moteur()
        torch = Mock()
        torch.cuda.is_available.return_value = False
        with patch.dict(sys.modules, {'torch': torch}), \
                patch('scripts.chatterbox_worker.charger_modele_local') as charger:
            conf = {'threads': 4, 'device': 'auto', 'modele': '/local/model'}
            moteur.charger(conf)
            moteur.charger(conf)
        charger.assert_called_once_with('/local/model', device='cpu')
        self.assertEqual(moteur.device, 'cpu')

    def test_echec_cuda_relance_sur_cpu_une_seule_fois(self):
        moteur = Moteur()
        moteur.device = 'cuda'
        with patch.object(moteur, 'charger') as charger, \
                patch.object(moteur, '_generer', side_effect=[RuntimeError('CUDA out of memory'), {'ok': True}]) as generer:
            self.assertTrue(moteur.generer({'device': 'auto'})['ok'])
            self.assertTrue(moteur.cuda_echec)
            charger.assert_any_call({'device': 'auto'}, force_cpu=True)
            self.assertEqual(generer.call_count, 2)

    def test_francais_parametres_cache_reference_et_conversion_pcm(self):
        moteur = Moteur()
        moteur.device = 'cpu'
        wav = Mock()
        wav.detach.return_value.cpu.return_value.numpy.return_value = np.array([[-2., 0., 2.]])
        moteur.modele = Mock(sr=24000, generate=Mock(return_value=wav))
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(sys.modules, {'torch': SimpleNamespace(inference_mode=nullcontext)}):
            ref = Path(tmp) / 'ref.wav'
            ref.write_bytes(b'fake-ref-for-unit-test')
            conf = dict(reference=str(ref), texte='Bonjour.', exaggeration=.2, cfg_weight=.45, temperature=.8)
            resultat = moteur._generer(conf)
            moteur._generer(conf)
            moteur.modele.prepare_conditionals.assert_called_once()
            moteur.modele.generate.assert_called_with('Bonjour.', language_id='fr', exaggeration=.2, cfg_weight=.45, temperature=.8)
            ref.write_bytes(b'changed-reference')
            moteur._generer(conf)
            self.assertEqual(moteur.modele.prepare_conditionals.call_count, 2)
        pcm = np.frombuffer(base64.b64decode(resultat['pcm']), dtype='<i2')
        np.testing.assert_array_equal(pcm, [-32767, 0, 32767])


if __name__ == '__main__':
    unittest.main()
