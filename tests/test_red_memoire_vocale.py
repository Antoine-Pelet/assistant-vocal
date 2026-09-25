"""Les secrets dictés ne passent jamais par le modèle, le HUD ou l'historique de conversation."""
import contextlib
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
from core.memoire_store import Magasin
from core import memoire_vocale


class VoixPriveeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.s=Magasin(Path(self.tmp.name)/'memoire.sqlite3',kdf={'memoryCost':65536,'timeCost':2})
        self.dire=Mock();self.lire=Mock()

    def tearDown(self):
        self.s.fermer();self.tmp.cleanup()

    def traiter(self,texte,reponses=(),accord=True):
        return memoire_vocale.traiter(texte,self.s,Mock(side_effect=reponses),Mock(return_value=accord),self.dire,self.lire)

    def initialiser(self):
        self.traiter("Red ouvre l'historique",['histoire orale secrète','histoire orale secrète'])

    def test_creation_et_acces_historique_oral(self):
        self.initialiser()
        self.assertTrue(self.s.acces_historique()['initialise'])
        self.assertFalse(self.s.acces_historique()['ouvert'])
        self.traiter("Red ouvre l'historique",['histoire orale secrète'])
        self.assertTrue(self.s.acces_historique()['ouvert'])
        self.assertNotIn('histoire orale secrète',repr(self.dire.call_args_list))

    def test_nouveau_secret_different_ou_accord_refuse_necrit_rien(self):
        self.traiter("ouvre l'historique",['premier secret','second secret'])
        self.assertFalse(self.s.acces_historique()['initialise'])
        self.traiter("ouvre l'historique",['premier secret','premier secret'],accord=False)
        self.assertFalse(self.s.acces_historique()['initialise'])

    def test_zone_orale_deverrouillage_et_changement(self):
        self.initialiser()
        self.traiter('crée une zone protégée Personnel',['mon premier secret','mon premier secret'])
        z=next(z for z in self.s.liste_zones() if z['id']!='generale')
        self.traiter('déverrouille la zone personnel',['mon premier secret'])
        self.assertTrue(self.s.crypto.ouverte(z['id']))
        self.traiter('change le mot de passe de la zone personnel',['mon premier secret','mon second secret','mon second secret'])
        self.assertFalse(self.s.crypto.ouverte(z['id']))
        self.traiter('déverrouille la zone personnel',['mon second secret'])
        self.assertTrue(self.s.crypto.ouverte(z['id']))
        self.traiter('verrouille la zone personnel')
        self.assertFalse(self.s.crypto.ouverte(z['id']))
        self.assertNotIn('mon premier secret',repr(self.dire.call_args_list))
        self.assertNotIn('mon second secret',repr(self.dire.call_args_list))

    def test_secret_inline_intercepte_avant_affichage_ou_modele(self):
        import jarvis14 as red
        import core.memoire as memoire
        historique=[]
        phrase='mon mot de passe est ULTRASECRET123'
        sortie=io.StringIO()
        with patch.object(memoire,'_MAGASIN',self.s),patch.object(red,'_hud') as hud, \
                patch.object(red,'_dire_en_vidant_micro'),patch.object(red,'repondre_en_ecoutant') as llm,contextlib.redirect_stdout(sortie):
            self.assertTrue(red.traiter(None,Mock(),historique,Mock(),Mock(),question=phrase))
        llm.assert_not_called();hud.assert_not_called();self.assertEqual(historique,[])
        self.assertNotIn('ULTRASECRET123',sortie.getvalue())

    def test_capture_audio_nettoyee_sans_log_et_sans_normaliser_secret(self):
        import jarvis14 as red
        audio=np.ones(3000,dtype=np.float32)
        whisper=Mock();whisper.transcribe.return_value=([SimpleNamespace(text='  SECRET exact !  ')],None)
        with patch.object(red,'_dire_en_vidant_micro'),patch.object(red,'bip'), \
                patch.object(red,'capturer',return_value=audio),patch.object(red,'_hud') as hud:
            secret=red._lire_secret_local(whisper,Mock(),'Quel est le mot de passe ?')
        self.assertEqual(secret,'SECRET exact !');self.assertTrue(np.all(audio==0));hud.assert_not_called()
        self.assertFalse(whisper.transcribe.call_args.kwargs['condition_on_previous_text'])

    def test_requete_ordinaire_non_interceptee(self):
        self.assertFalse(self.traiter('quelle heure est-il'))

    def test_sapi_confidentiel_ne_journalise_pas_son_stderr(self):
        import jarvis14 as red
        p=Mock(returncode=1);p.communicate.return_value=(None,b'SECRET_ERROR_TEXT')
        sortie=io.StringIO()
        with patch.object(red.subprocess,'Popen',return_value=p),patch.object(red,'_est_interrompu',return_value=False),contextlib.redirect_stdout(sortie):
            red._dire_sapi('SECRET_ERROR_TEXT',confidentiel=True)
        self.assertNotIn('SECRET_ERROR_TEXT',sortie.getvalue())

    def test_sapi_revoque_pendant_creation_processus_ne_recoit_pas_de_texte(self):
        import jarvis14 as red
        p=Mock()
        with patch.object(red.subprocess,'Popen',return_value=p),patch.object(red,'_est_interrompu',side_effect=[False,True]):
            red._dire_sapi('SECRET_A_NE_PAS_ENVOYER',confidentiel=True)
        p.terminate.assert_called_once();p.communicate.assert_called_once_with()


if __name__=='__main__':unittest.main()
