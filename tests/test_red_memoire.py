"""Validation, persistance, chiffrement, expiration et intégration réelle du panneau."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core import memoire, registre
from core.memoire_store import Magasin, ErreurMemoire, SEPT_JOURS, accord_explicite
from tools import memoire as outils


class MemoireTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.chemin = Path(self.tmp.name) / 'memoire.sqlite3'
        self.temps = 1_700_000_000.0
        self.store = Magasin(self.chemin, horloge=lambda: self.temps, duree_session=60,kdf={'memoryCost':65536,'timeCost':2})
        h=self.store.preparer('historique_initialiser',{'mot_de_passe':'historique test'})
        self.store.confirmer(h['jeton'])
        self.patch = patch.object(memoire, '_MAGASIN', self.store)
        self.patch.start()
        self.ancien_pending = registre._EN_ATTENTE
        registre._EN_ATTENTE = None

    def tearDown(self):
        registre.annuler_confirme()
        registre._EN_ATTENTE = self.ancien_pending
        self.patch.stop()
        self.store.fermer()
        self.tmp.cleanup()

    def valider(self, action, **valeurs):
        p = self.store.preparer(action, valeurs)
        self.store.confirmer(p['jeton'])
        return p

    def journal(self):
        self.store.debloquer('_historique','historique test')
        return self.store.historique()

    def zone(self, protege=False, **valeurs):
        self.valider('zone_creer', nom='Privée', mot_de_passe_action='definir' if protege else 'garder',
                     mot_de_passe='mot de passe test', **valeurs)
        z = next(z for z in self.store.etat()['zones'] if z['id'] != 'generale')
        if protege:
            self.store.debloquer(z['id'], 'mot de passe test')
        return z['id']

    def test_proposition_necrit_pas_et_accord_usage_unique(self):
        p = self.store.preparer('ajouter', {'contenu':'thé', 'categorie':'facts'})
        self.assertEqual(memoire.charger()['facts'], [])
        self.assertEqual(self.journal(), [])
        self.store.confirmer(p['jeton'])
        self.assertEqual(memoire.charger()['facts'], ['thé'])
        with self.assertRaises(ErreurMemoire): self.store.confirmer(p['jeton'])

    def test_refus_silence_et_negation(self):
        for phrase in ('', 'non', 'oui mais non', 'ne confirme pas', 'toujours', 'pas toujours', 'je ne suis pas d accord', 'pourquoi'):
            self.assertFalse(accord_explicite(phrase), phrase)
        for phrase in ('Oui.', "D’accord", 'je confirme', 'oui toujours'):
            self.assertTrue(accord_explicite(phrase), phrase)

    def test_migration_et_redemarrage(self):
        ancien = Path(self.tmp.name) / 'memory.json'
        ancien.write_text(json.dumps({'preferences':{'boisson':'thé'}, 'facts':['un souvenir']}), encoding='utf-8')
        autre = Path(self.tmp.name) / 'migration.sqlite3'
        store = Magasin(autre, ancien)
        self.assertEqual(store.contexte()[1]['preferences'], {'boisson':'thé'})
        self.assertEqual(Magasin(autre, ancien).contexte()[1]['facts'], ['un souvenir'])
        self.assertTrue(ancien.exists())

    def test_ancien_format_faits_et_erreur_sans_perte(self):
        ancien = Path(self.tmp.name) / 'ancien.json'
        ancien.write_text('{"faits":["souvenir"]}', encoding='utf-8')
        self.assertEqual(Magasin(Path(self.tmp.name)/'a.db', ancien).contexte()[1]['facts'], ['souvenir'])
        ancien.write_text('INVALIDE', encoding='utf-8')
        with self.assertRaises(ErreurMemoire): Magasin(Path(self.tmp.name)/'b.db', ancien)
        self.assertEqual(ancien.read_text(), 'INVALIDE')

    def test_ajout_modification_suppression_tous_valides(self):
        self.valider('ajouter', categorie='preferences', cle='boisson', contenu='thé')
        p = self.store.preparer('ajouter', dict(categorie='preferences', cle='boisson', contenu='café'))
        self.assertIn('thé', p['resume']); self.assertIn('café', p['resume'])
        self.assertEqual(memoire.charger()['preferences']['boisson'], 'thé')
        self.store.confirmer(p['jeton'])
        p = self.store.preparer('oublier', {'sujet':'café'})
        self.assertEqual(memoire.charger()['preferences']['boisson'], 'café')
        self.store.confirmer(p['jeton'])
        self.assertEqual(memoire.charger()['preferences'], {})
        self.assertEqual([h['action'] for h in self.journal()], ['supprimer','modifier','ajouter'])

    def test_proposition_immuable_et_perimee(self):
        valeurs = {'contenu':'original'}
        p = self.store.preparer('ajouter', valeurs)
        valeurs['contenu'] = 'falsifié'; p['detail']['apres']['contenu'] = 'falsifié'
        self.store.confirmer(p['jeton'])
        self.assertEqual(memoire.charger()['facts'], ['original'])
        p = self.store.preparer('ajouter', {'contenu':'périmé'})
        self.temps += 300
        with self.assertRaises(ErreurMemoire): self.store.confirmer(p['jeton'])

    def test_modification_concurrente_exige_nouvel_accord(self):
        p1 = self.store.preparer('ajouter', {'contenu':'un'})
        p2 = self.store.preparer('ajouter', {'contenu':'deux'})
        self.store.confirmer(p2['jeton'])
        with self.assertRaises(ErreurMemoire): self.store.confirmer(p1['jeton'])
        self.assertEqual(memoire.charger()['facts'], ['deux'])

    def test_origines_isolees_et_annulation(self):
        p = self.store.preparer('ajouter', {'contenu':'test'}, origine='voix')
        with self.assertRaises(ErreurMemoire): self.store.confirmer(p['jeton'])
        self.store.annuler(p['jeton'], origine='voix')
        with self.assertRaises(ErreurMemoire): self.store.confirmer(p['jeton'], origine='voix')

    def test_transaction_historique_et_memoire_atomique(self):
        with self.store._connexion() as db:
            db.execute("CREATE TRIGGER test_echec BEFORE INSERT ON historique_chiffre BEGIN SELECT RAISE(ABORT,'test'); END")
        p = self.store.preparer('ajouter', {'contenu':'pas enregistré'})
        with self.assertRaises(sqlite3.IntegrityError): self.store.confirmer(p['jeton'])
        self.assertEqual(memoire.charger()['facts'], [])

    def test_historique_immuable_et_frontiere_exacte(self):
        self.valider('ajouter', contenu='test')
        with self.store._connexion() as db:
            with self.assertRaises(sqlite3.IntegrityError): db.execute("UPDATE historique_chiffre SET evenement='altéré'")
            with self.assertRaises(sqlite3.IntegrityError): db.execute('DELETE FROM historique_chiffre')
        self.temps += SEPT_JOURS - .001
        self.assertEqual(len(self.journal()), 1)
        self.temps += .001
        self.assertEqual(self.journal(), [])
        with self.store._connexion() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM historique_chiffre').fetchone()[0], 0)
        self.assertEqual(memoire.charger()['facts'], ['test'])

    def test_expiration_individuelle_pas_une_purge_hebdomadaire(self):
        self.valider('ajouter', contenu='un'); self.temps += 120
        self.valider('ajouter', contenu='deux'); self.temps += SEPT_JOURS - 120
        self.assertEqual(len(self.journal()), 1)
        self.temps += 120
        self.assertEqual(self.journal(), [])

    def test_purge_redemarrage_et_pas_de_restauration_des_propositions(self):
        self.valider('ajouter', contenu='durable')
        p = self.store.preparer('ajouter', {'contenu':'en attente'})
        self.temps += SEPT_JOURS
        store = Magasin(self.chemin, horloge=lambda:self.temps)
        store.debloquer('_historique','historique test')
        self.assertEqual(store.historique(), [])
        self.assertEqual(store.contexte()[1]['facts'], ['durable'])
        with self.assertRaises(ErreurMemoire): store.confirmer(p['jeton'])

    def test_mot_de_passe_chiffrement_et_absence_dans_historique(self):
        zid = self.zone(True)
        self.valider('ajouter', zone=zid, contenu='SECRET_MEMOIRE_123456')
        self.assertIn('SECRET_MEMOIRE_123456', [e['contenu'] for e in self.store.consulter(zid)])
        self.assertNotIn('SECRET_MEMOIRE_123456', repr(self.journal()))
        self.assertNotIn(b'SECRET_MEMOIRE_123456', self.chemin.read_bytes())
        self.assertNotIn(b'mot de passe test', self.chemin.read_bytes())
        self.store.bloquer(zid)
        self.assertNotIn('SECRET_MEMOIRE_123456', repr(self.store.etat()))
        with self.assertRaises(ErreurMemoire): self.store.debloquer(zid, 'incorrect')
        self.store.debloquer(zid, 'mot de passe test')
        self.assertIn('SECRET_MEMOIRE_123456', [e['contenu'] for e in self.store.consulter(zid)])
        self.assertNotIn('SECRET_MEMOIRE_123456', repr(memoire.charger()))
        self.assertNotIn('SECRET_MEMOIRE_123456', repr(Magasin(self.chemin).etat()))

    def test_session_et_dates_cumulatives(self):
        zid = self.zone(True, debut=self.temps+10, fin=self.temps+30)
        self.assertFalse(next(z for z in self.store.etat()['zones'] if z['id']==zid)['accessible'])
        self.temps += 10
        self.valider('ajouter', zone=zid, contenu='temporaire')
        p = self.store.preparer('ajouter', dict(zone=zid, contenu='trop tard'))
        self.temps += 20
        self.assertNotIn('temporaire', repr(self.store.contexte(True)))
        with self.assertRaises(ErreurMemoire): self.store.confirmer(p['jeton'])

    def test_session_expire_et_verrouillage_annule_proposition(self):
        zid = self.zone(True)
        p = self.store.preparer('ajouter', dict(zone=zid, contenu='non'))
        self.store.bloquer(zid)
        self.store.debloquer(zid, 'mot de passe test')
        with self.assertRaises(ErreurMemoire): self.store.confirmer(p['jeton'])
        self.temps += 60
        with self.assertRaises(ErreurMemoire): self.store.preparer('ajouter', dict(zone=zid, contenu='non'))

    def test_changement_mot_de_passe_et_suppression_exigent_accord(self):
        zid = self.zone(True)
        self.valider('ajouter', zone=zid, contenu='à préserver')
        p = self.store.preparer('zone_modifier', dict(zone=zid, nom='Privée', mot_de_passe_action='definir', mot_de_passe='nouveau passe', ancien_mot_de_passe='mot de passe test'))
        self.store.confirmer(p['jeton'])
        with self.assertRaises(ErreurMemoire): self.store.debloquer(zid, 'mot de passe test')
        self.store.debloquer(zid, 'nouveau passe')
        self.assertIn('à préserver', [e['contenu'] for e in self.store.consulter(zid)])
        p = self.store.preparer('zone_supprimer', dict(zone=zid))
        self.assertEqual(len(self.store.etat()['zones']), 2)
        self.store.confirmer(p['jeton']); self.assertEqual(len(self.store.etat()['zones']), 1)

    def test_dates_invalides_et_limitation_essais(self):
        for debut, fin in ((10,10),(20,10),('2026-09-23T12:00:00',None), (float('nan'),None)):
            with self.assertRaises(ErreurMemoire): self.store.preparer('zone_creer', dict(nom='test',debut=debut,fin=fin))
        zid = self.zone(True); self.store.bloquer(zid)
        for _ in range(5):
            with self.assertRaises(ErreurMemoire): self.store.debloquer(zid, 'mauvais')
        with self.assertRaisesRegex(ErreurMemoire, 'Trop'): self.store.debloquer(zid, 'mot de passe test')
        self.temps += 60; self.store.debloquer(zid, 'mot de passe test')

    def test_registre_toujours_interdit_et_appel_direct_sans_effet(self):
        self.assertEqual(registre.niveau('remember'), 'N3')
        self.assertEqual(registre.niveau('forget'), 'N3')
        with patch('core.config.reglage', return_value=['remember','forget']):
            self.assertFalse(registre.est_autorise('remember'))
        self.assertFalse(registre.autoriser_toujours('remember'))
        outils.remember('fait', 'sans accord'); outils.forget('test')
        with self.assertRaises(ErreurMemoire): memoire.sauver({})
        self.assertEqual(memoire.charger()['facts'], [])

    def test_registre_proposition_revue_confirmation_et_refus(self):
        registre.mettre_en_attente(registre.get('remember'), dict(categorie='fait', contenu='du thé'))
        self.assertIn('du thé', registre.annonce_en_attente())
        self.assertEqual(memoire.charger()['facts'], [])
        registre.executer_confirme(memoriser=True)
        self.assertEqual(memoire.charger()['facts'], ['du thé'])
        registre.mettre_en_attente(registre.get('forget'), dict(sujet='thé'))
        self.assertIn('du thé', registre.annonce_en_attente())
        registre.annuler_confirme()
        self.assertEqual(memoire.charger()['facts'], ['du thé'])

    def test_contexte_retiré_apres_verrouillage(self):
        import jarvis14 as red
        zid = self.zone(True)
        self.valider('ajouter', zone=zid, contenu='SECRET_LOCAL')
        with patch.object(red, '_SIGNATURE_MEMOIRE', None), patch.object(red, 'SYSTEME_COURANT', ''):
            hist = [{'role':'user','content':'bonjour'}]
            red._actualiser_memoire(hist, True)
            self.assertNotIn('SECRET_LOCAL', red.SYSTEME_COURANT)
            hist.append({'role':'user','content':'suite'})
            self.store.bloquer(zid)
            red._actualiser_memoire(hist, True)
            self.assertNotIn('SECRET_LOCAL', red.SYSTEME_COURANT)
            self.assertNotIn('SECRET_LOCAL',repr(hist))

    def client(self):
        from core.panneau import monter_routes
        app = FastAPI(); monter_routes(app)
        return TestClient(app, base_url='http://127.0.0.1:8790', client=('127.0.0.1',12345))

    def test_api_deux_etapes_et_historique_lecture_seule(self):
        with self.client() as client:
            base = '/api/panneau/memoire'
            r=client.post(base+'/proposer', json={'action':'ajouter','valeurs':{'contenu':'API test'}})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(memoire.charger()['facts'], [])
            self.assertEqual(client.post(base+'/confirmer', json={'jeton':r.json()['jeton']}).status_code, 200)
            self.assertEqual(memoire.charger()['facts'], ['API test'])
            self.store.debloquer('_historique','historique test')
            self.assertEqual(client.get(base+'/historique').headers['cache-control'], 'no-store')
            self.assertEqual(client.post(base+'/historique',json={}).status_code, 400)
            self.assertEqual(client.delete(base+'/historique').status_code, 405)
            self.assertEqual(client.get('/panneau/memoire.js').status_code, 200)

    def test_api_refuse_csrf_tunnel_et_origines(self):
        with self.client() as c:
            base='/api/panneau/memoire'
            for headers in ({'origin':'https://example.org'}, {'x-forwarded-for':'1.2.3.4'}, {'host':'example.org'}, {'sec-fetch-site':'cross-site'}):
                self.assertEqual(c.get(base,headers=headers).status_code, 403)
            self.assertEqual(c.post(base+'/proposer', content='{}').status_code, 415)
            self.assertEqual(c.post(base+'/proposer', content='no',headers={'content-type':'application/json'}).status_code, 400)
            self.assertEqual(c.post(base+'/proposer', json=[]).status_code, 400)
            self.assertEqual(c.post(base+'/proposer', json={'texte':'x'*40000}).status_code, 413)
            self.assertEqual(c.post(base+'/confirmer', json={'jeton':'inventé'}).status_code, 400)
            self.assertEqual(c.post(base+'/confirmer', json={'jeton':[]}).status_code, 400)
            self.assertEqual(c.post(base+'/proposer', json={'action':'ajouter','valeurs':{'zone':[]}}).status_code, 400)

    def test_purge_effective_en_arriere_plan_sans_consultation(self):
        self.valider('ajouter', contenu='test')
        self.store.demarrer()
        self.temps += SEPT_JOURS
        self.store.reveil.set()
        limite=time.monotonic()+3
        while time.monotonic()<limite:
            with self.store._connexion() as db:
                nombre=db.execute('SELECT COUNT(*) FROM historique_chiffre').fetchone()[0]
            if nombre==0:break
            time.sleep(.02)
        self.assertEqual(nombre,0)

    def test_controleur_vocal_refuse_negation_et_accepte_accord(self):
        import jarvis14 as red
        for phrase, attendu in [('non toujours',False),('oui mais non',False),('oui',True)]:
            registre.mettre_en_attente(registre.get('remember'),dict(categorie='fait',contenu='accord vocal'))
            whisper=SimpleNamespace(transcribe=lambda *a, **k:([SimpleNamespace(text=phrase)],None))
            with patch.object(red,'capturer',return_value=object()), patch.object(red,'_hud'), \
                    patch.object(red,'_dire_en_vidant_micro'), patch.object(red,'_est_interrompu',return_value=False):
                red._confirmer(False,False,whisper,[],None)
            self.assertEqual('accord vocal' in memoire.charger()['facts'],attendu)

    def test_pas_de_perte_lors_dune_collision_detiquettes(self):
        self.valider('ajouter',categorie='preferences',cle='boisson',contenu='thé')
        self.valider('ajouter',categorie='preferences',cle='couleur',contenu='bleu')
        entrees=self.store.etat()['zones'][0]['entrees']
        cible=next(e for e in entrees if e['cle']=='couleur')
        with self.assertRaises(ErreurMemoire):
            self.store.preparer('modifier',dict(id=cible['id'],categorie='preferences',cle='boisson',contenu='vert'))
        self.assertEqual(memoire.charger()['preferences'],{'boisson':'thé','couleur':'bleu'})

    def test_memoire_illimitee_et_suppression_explicitement_programmee(self):
        self.valider('ajouter',contenu='illimité')
        p=self.store.preparer('ajouter',dict(contenu='temporaire',expiration=self.temps+10))
        self.assertIn('Suppression programmée',p['resume'])
        self.store.confirmer(p['jeton'])
        self.temps+=10;self.store.purger()
        self.assertEqual(memoire.charger()['facts'],['illimité'])
        self.temps+=10*365*86400;self.store.purger()
        self.assertEqual(memoire.charger()['facts'],['illimité'])

    def test_historique_chiffre_ferme_reste_alimentable_et_expire(self):
        self.store.bloquer('_historique')
        self.valider('ajouter',contenu='souvenir privé journal')
        with self.assertRaises(ErreurMemoire):self.store.historique()
        with self.store._connexion() as db:
            brut=db.execute('SELECT evenement FROM historique_chiffre').fetchone()[0]
            self.assertNotIn('generale',brut);self.assertNotIn('ajouter',brut)
        self.assertEqual(len(self.journal()),1)
        self.store.bloquer('_historique');self.temps+=SEPT_JOURS;self.store.purger()
        self.assertEqual(self.journal(),[])

    def test_changement_password_atomique_ciphertexts_identiques(self):
        zid=self.zone(True)
        self.valider('ajouter',zone=zid,contenu='intact')
        with self.store._connexion() as db:avant=self.store._zone(db,zid)
        p=self.store.preparer('zone_modifier',dict(zone=zid,nom='Privée',mot_de_passe_action='definir',
                            ancien_mot_de_passe='mot de passe test',mot_de_passe='nouvelle phrase'))
        with patch.object(self.store,'_journaliser',side_effect=sqlite3.OperationalError('simulated failure')):
            with self.assertRaises(sqlite3.OperationalError):self.store.confirmer(p['jeton'])
        with self.store._connexion() as db:apres=self.store._zone(db,zid)
        self.assertEqual(avant['crypto'],apres['crypto']);self.assertEqual(avant['donnees'],apres['donnees'])
        self.store.debloquer(zid,'mot de passe test')
        self.valider('zone_modifier',zone=zid,nom='Privée',mot_de_passe_action='definir',
                     ancien_mot_de_passe='mot de passe test',mot_de_passe='nouvelle phrase')
        with self.store._connexion() as db:apres=self.store._zone(db,zid)
        self.assertNotEqual(avant['crypto'],apres['crypto']);self.assertEqual(avant['donnees'],apres['donnees'])

    def test_password_historique_remplace_sans_rechiffrer_evenements(self):
        self.valider('ajouter',contenu='test')
        with self.store._connexion() as db:avant=list(db.execute('SELECT id,evenement FROM historique_chiffre'))
        self.valider('historique_mot_de_passe',ancien_mot_de_passe='historique test',mot_de_passe='nouvel historique')
        with self.assertRaises(ErreurMemoire):self.store.debloquer('_historique','historique test')
        self.store.debloquer('_historique','nouvel historique')
        self.assertEqual(len(self.store.historique()),2)
        with self.store._connexion() as db:
            self.assertEqual(avant[0]['evenement'],db.execute('SELECT evenement FROM historique_chiffre WHERE id=?',(avant[0]['id'],)).fetchone()[0])

    def test_rate_limiting_reste_apres_redemarrage(self):
        for _ in range(5):
            with self.assertRaises(ErreurMemoire):self.store.debloquer('_historique','incorrect')
        reprise=Magasin(self.chemin,horloge=lambda:self.temps)
        with self.assertRaisesRegex(ErreurMemoire,'Trop'):reprise.debloquer('_historique','historique test')
        reprise.fermer()

    def test_zone_future_conditions_modifiables_avec_password_sans_dechiffrer_contenu(self):
        zid=self.zone(True,debut=self.temps+1000)
        self.store.purger();self.assertFalse(self.store.crypto.ouverte(zid))
        self.valider('zone_modifier',zone=zid,nom='Privée',debut=None,fin=None,
                     ancien_mot_de_passe='mot de passe test',mot_de_passe_action='garder')
        self.store.debloquer(zid,'mot de passe test')
        self.assertEqual(self.store.consulter(zid),[])

    def test_migration_ancienne_zone_scrypt_aes_apres_authentification(self):
        import base64,os
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
        sel=os.urandom(16);nonce=os.urandom(12)
        cle=Scrypt(salt=sel,length=32,n=2**15,r=8,p=1).derive(b'ancienne phrase')
        entrees=[dict(id='ancienne-info',categorie='facts',cle='',contenu='souvenir migré')]
        donnees=base64.b64encode(nonce+AESGCM(cle).encrypt(nonce,json.dumps(entrees).encode(),b'legacy')).decode()
        with self.store._connexion() as db:
            db.execute('INSERT INTO zones VALUES (?,?,?,?,?,?,?,?)',('legacy','Ancienne',None,None,
                base64.b64encode(sel).decode(),donnees,1,json.dumps({'cryptoVersion':0,'algorithm':'legacy-aes256-gcm-scrypt'})))
        with self.assertRaises(ErreurMemoire):self.store.debloquer('legacy','incorrect')
        with self.store._connexion() as db:self.assertEqual(self.store._zone(db,'legacy')['donnees'],donnees)
        self.store.debloquer('legacy','ancienne phrase')
        self.assertEqual(self.store.consulter('legacy')[0]['contenu'],'souvenir migré')
        with self.store._connexion() as db:
            z=self.store._zone(db,'legacy')
            self.assertIsNone(z['sel']);self.assertEqual(json.loads(z['crypto'])['cryptoVersion'],1)
            self.assertNotIn('souvenir migré',z['donnees'])

    def test_premier_password_historique_migre_sans_renouveler_les_dates(self):
        autre=Magasin(Path(self.tmp.name)/'historique-v1.db',horloge=lambda:self.temps,kdf={'memoryCost':65536,'timeCost':2})
        with autre._connexion() as db:
            db.execute('INSERT INTO historique(cree,expire,evenement) VALUES (?,?,?)',
                (self.temps-60,self.temps-60+SEPT_JOURS,json.dumps({'action':'ajouter','zone':'ancienne','elements':[]})))
        with self.assertRaises(ErreurMemoire):autre.historique()
        p=autre.preparer('historique_initialiser',{'mot_de_passe':'nouveau journal'})
        self.assertFalse(autre.acces_historique()['initialise'])
        autre.confirmer(p['jeton']);autre.debloquer('_historique','nouveau journal')
        hist=autre.historique();self.assertEqual(hist[0]['cree'],self.temps-60)
        self.assertEqual(hist[0]['expire'],self.temps-60+SEPT_JOURS)
        with autre._connexion() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM historique').fetchone()[0],0)
        autre.fermer()

    def test_aucun_changement_sans_configuration_initiale_historique(self):
        autre=Magasin(Path(self.tmp.name)/'sans-historique.db')
        with self.assertRaisesRegex(ErreurMemoire,"mot de passe de l'historique"):
            autre.preparer('ajouter',{'contenu':'interdit sans journal chiffré'})
        self.assertEqual(autre.contexte()[1]['facts'],[]);autre.fermer()


if __name__ == '__main__':
    unittest.main()
