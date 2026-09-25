"""Tests de la couche isolée, sans base, API, modèle ou microphone."""
import copy
import unittest
from core.memoire_crypto import Coffre, ErreurCrypto, deb64, b64, canonique

PARAMS = dict(memoryCost=65536, timeCost=2, parallelism=1, algorithmVersion=19)


class CryptoTests(unittest.TestCase):
    def setUp(self):
        self.c = Coffre()
        self.h = self.c.creer('zone-a', 'mot de passe A', PARAMS)

    def tearDown(self):
        self.c.fermer()

    def element(self):
        return self.c.chiffrer('zone-a', 'memoire-a', {'secret': 'donnée confidentielle'})

    def test_bon_mot_de_passe_apres_verrouillage(self):
        e=self.element();self.c.verrouiller('zone-a')
        with self.assertRaises(ErreurCrypto): self.c.dechiffrer('zone-a','memoire-a',e)
        self.c.deverrouiller('zone-a',self.h,'mot de passe A')
        self.assertEqual(self.c.dechiffrer('zone-a','memoire-a',e),{'secret':'donnée confidentielle'})

    def test_mauvais_mot_de_passe_ne_retourne_rien(self):
        e=self.element()
        with self.assertRaisesRegex(ErreurCrypto,'incorrect ou données invalides'):
            self.c.deverrouiller('zone-a',self.h,'mauvais')
        self.assertFalse(self.c.ouverte('zone-a'))
        with self.assertRaises(ErreurCrypto): self.c.dechiffrer('zone-a','memoire-a',e)

    def test_alteration_ciphertext_et_nonce(self):
        for champ in ('ciphertext','nonce'):
            e=self.element();brut=bytearray(deb64(e['encryption'][champ]));brut[0]^=1;e['encryption'][champ]=b64(brut)
            with self.assertRaises(ErreurCrypto): self.c.dechiffrer('zone-a','memoire-a',e)

    def test_aad_identifiants_type_et_metadata(self):
        e=self.element()
        for zid,mid in [('zone-b','memoire-a'),('zone-a','memoire-b')]:
            autre=copy.deepcopy(e);autre['zoneId']=zid;autre['id']=mid
            # Même DEK pour isoler le test AAD du simple refus « zone verrouillée ».
            if zid=='zone-b': self.c._cles[zid]=self.c._cles['zone-a']
            with self.assertRaises(ErreurCrypto): self.c.dechiffrer(zid,mid,autre)
            if zid=='zone-b': self.c._cles.pop(zid)
        with self.assertRaises(ErreurCrypto): self.c.dechiffrer('zone-a','memoire-a',e,'preview')
        with self.assertRaises(ErreurCrypto): self.c.dechiffrer('zone-a','memoire-a',e,extra={'x':1})

    def test_changer_password_ne_change_pas_ciphertexts(self):
        e=self.element();original=copy.deepcopy(e)
        h2=self.c.changer_mot_de_passe('zone-a',self.h,'mot de passe A','mot de passe B',PARAMS)
        self.c.verrouiller('zone-a')
        with self.assertRaises(ErreurCrypto): self.c.deverrouiller('zone-a',h2,'mot de passe A')
        self.c.deverrouiller('zone-a',h2,'mot de passe B')
        self.assertEqual(self.c.dechiffrer('zone-a','memoire-a',e)['secret'],'donnée confidentielle')
        self.assertEqual(e,original)
        self.assertNotEqual(self.h['kdf']['salt'],h2['kdf']['salt'])
        self.assertNotEqual(self.h['wrappedKey'],h2['wrappedKey'])

    def test_changement_exige_ancien_password_meme_zone_ouverte(self):
        with self.assertRaises(ErreurCrypto): self.c.changer_mot_de_passe('zone-a',self.h,'incorrect','nouveau mot',PARAMS)
        self.assertTrue(self.c.ouverte('zone-a'))

    def test_zones_meme_password_cles_sels_et_enveloppes_independants(self):
        h2=self.c.creer('zone-b','mot de passe A',PARAMS)
        self.assertNotEqual(self.h['kdf']['salt'],h2['kdf']['salt'])
        self.assertNotEqual(self.h['wrappedKey'],h2['wrappedKey'])
        e=self.element();e['zoneId']='zone-b'
        with self.assertRaises(ErreurCrypto): self.c.dechiffrer('zone-b','memoire-a',e)
        from nacl._sodium import ffi
        self.assertNotEqual(ffi.buffer(self.c._cles['zone-a'].ptr,32)[:],ffi.buffer(self.c._cles['zone-b'].ptr,32)[:])

    def test_nonce_nouveau_a_chaque_chiffrement(self):
        nonces={self.element()['encryption']['nonce'] for _ in range(100)}
        self.assertEqual(len(nonces),100)
        self.assertTrue(all(len(deb64(n))==24 for n in nonces))

    def test_memzero_et_retrait_de_la_cle(self):
        from nacl._sodium import ffi
        cle=self.c._cles['zone-a'];self.c.verrouiller('zone-a')
        self.assertTrue(cle.ferme);self.assertEqual(ffi.buffer(cle.ptr,32)[:],bytes(32))
        self.assertNotIn('zone-a',self.c._cles)

    def test_entete_alteree_version_et_parametres_bornes(self):
        for chemin,valeur in [('cryptoVersion',99),('parallelism',2),('memoryCost',2**40),('timeCost',0),('algorithmVersion',16)]:
            h=copy.deepcopy(self.h)
            if chemin=='cryptoVersion':h[chemin]=valeur
            else:h['kdf'][chemin]=valeur
            with self.assertRaises(ErreurCrypto): self.c.deverrouiller('zone-a',h,'mot de passe A')
        h=copy.deepcopy(self.h);h['kdf']['memoryCost']=131072
        with self.assertRaises(ErreurCrypto): self.c.deverrouiller('zone-a',h,'mot de passe A')

    def test_serialisation_canonique(self):
        self.assertEqual(canonique({'b':2,'a':1}),canonique({'a':1,'b':2}))

    def test_depot_historique_verrouille_et_aad_dates(self):
        h=self.c.creer_journal('historique privé',PARAMS);self.c.verrouiller('_historique')
        e=self.c.deposer_evenement(h,'event1',{'action':'ajouter'},100,604900)
        self.assertNotIn('ajouter',repr(e))
        with self.assertRaises(ErreurCrypto):self.c.lire_evenement(h,'event1',e,100,604900)
        self.c.deverrouiller('_historique',h,'historique privé')
        self.assertEqual(self.c.lire_evenement(h,'event1',e,100,604900),{'action':'ajouter'})
        for ident,t1,t2 in [('autre',100,604900),('event1',101,604901),('event1',100,604901)]:
            with self.assertRaises(ErreurCrypto):self.c.lire_evenement(h,ident,e,t1,t2)

    def test_password_nulle_part_dans_structures_persistables(self):
        self.assertNotIn('mot de passe A',repr(self.h))
        self.assertNotIn('donnée confidentielle',repr(self.element()))


if __name__=='__main__':unittest.main()
