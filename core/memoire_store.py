"""Mémoire locale transactionnelle. Toute mutation passe par une proposition à usage unique.

L'historique ne contient que des métadonnées : aucune copie des souvenirs protégés.
Les mots de passe ne quittent jamais ce processus et ne sont pas enregistrés.
"""
import copy
import json
import math
import secrets
import sqlite3
import threading
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from core.memoire_crypto import Coffre, ErreurCrypto, ERREUR_AUTH, parametres

SEPT_JOURS = 7 * 24 * 60 * 60
CATEGORIES = ("preferences", "people", "projects", "facts")


class ErreurMemoire(ValueError):
    pass


def normaliser(texte):
    return "".join(c for c in unicodedata.normalize("NFD", str(texte).lower())
                   if unicodedata.category(c) != "Mn")


def accord_explicite(texte):
    """Une négation, le silence ou une phrase ambiguë ne valent jamais un accord."""
    plat = " ".join("".join(c if c.isalnum() else " " for c in normaliser(texte)).split())
    return plat in {"oui", "oui je confirme", "je confirme", "confirme", "ok", "d accord",
                    "vas y", "oui fais le", "oui tu peux", "oui monsieur", "oui red", "oui toujours"}


def date_utc(valeur):
    if valeur in (None, ""):
        return None
    try:
        if isinstance(valeur, str):
            date = datetime.fromisoformat(valeur.replace("Z", "+00:00"))
            if date.tzinfo is None:
                raise ValueError()
            valeur = date.timestamp()
        valeur = float(valeur)
        if not math.isfinite(valeur):
            raise ValueError()
        return valeur
    except (ValueError, TypeError, OverflowError):
        raise ErreurMemoire("La date doit inclure son fuseau horaire.") from None


def _texte(valeur, maximum=4000):
    if not isinstance(valeur, str) or not valeur.strip() or len(valeur) > maximum:
        raise ErreurMemoire(f"Texte requis, limité à {maximum} caractères.")
    return valeur.strip()


class Magasin:
    def __init__(self, fichier, ancien=None, horloge=time.time, duree_session=900, kdf=None):
        self.fichier = Path(fichier)
        self.horloge = horloge
        self.duree_session = max(60, min(int(duree_session), 3600))
        self.verrou = threading.RLock()
        self.propositions = {}
        self.sessions = {}  # dates et versions publiques seulement, jamais de clés
        self.crypto = Coffre()
        self.kdf = parametres(kdf)
        self.generation = 0
        self.observateurs = []
        self.echecs = {}
        self.reveil = threading.Event()
        self.arret = threading.Event()
        self.fil = None
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        with self._connexion() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS zones (
                    id TEXT PRIMARY KEY, nom TEXT NOT NULL, debut REAL, fin REAL,
                    sel TEXT, donnees TEXT NOT NULL, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS historique (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, cree REAL NOT NULL,
                    expire REAL NOT NULL CHECK (expire = cree + 604800),
                    evenement TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS expiration ON historique(expire);
                CREATE TRIGGER IF NOT EXISTS historique_immuable
                    BEFORE UPDATE ON historique BEGIN
                    SELECT RAISE(ABORT, 'Historique en lecture seule'); END;
                CREATE TRIGGER IF NOT EXISTS historique_retention
                    BEFORE DELETE ON historique WHEN OLD.expire > red_now() BEGIN
                    SELECT RAISE(ABORT, 'Retention de sept jours'); END;
                CREATE TABLE IF NOT EXISTS metadata (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL);
            """)
            db.executescript("""
                CREATE TABLE IF NOT EXISTS historique_chiffre (
                    id TEXT PRIMARY KEY, cree REAL NOT NULL, expire REAL NOT NULL
                    CHECK (expire = cree + 604800), evenement TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS expiration_chiffree ON historique_chiffre(expire);
                CREATE TRIGGER IF NOT EXISTS historique_chiffre_immuable BEFORE UPDATE ON historique_chiffre
                    BEGIN SELECT RAISE(ABORT, 'Historique en lecture seule'); END;
                CREATE TRIGGER IF NOT EXISTS historique_chiffre_retention BEFORE DELETE ON historique_chiffre
                    WHEN OLD.expire > red_now() BEGIN SELECT RAISE(ABORT, 'Retention de sept jours'); END;
                CREATE TABLE IF NOT EXISTS acces_echecs (zone TEXT PRIMARY KEY, nombre INTEGER, attente REAL);
            """)
            colonnes = {r[1] for r in db.execute('PRAGMA table_info(zones)')}
            if 'crypto' not in colonnes:
                db.execute('ALTER TABLE zones ADD COLUMN crypto TEXT')
                db.execute("UPDATE zones SET crypto=? WHERE sel IS NOT NULL", (json.dumps({
                    "cryptoVersion": 0, "algorithm": "legacy-aes256-gcm-scrypt"}),))
            if not db.execute("SELECT 1 FROM metadata WHERE cle='initialise'").fetchone():
                entrees = self._importer(ancien)
                db.execute("INSERT INTO zones(id,nom,debut,fin,sel,donnees,revision) VALUES (?,?,?,?,?,?,?)",
                           ("generale", "Générale", None, None, None,
                            json.dumps(entrees, ensure_ascii=False), 1))
                db.execute("INSERT INTO metadata VALUES ('initialise', '1')")
        self.purger()

    @contextmanager
    def _connexion(self):
        db = sqlite3.connect(self.fichier, timeout=10)
        db.row_factory = sqlite3.Row
        db.create_function("red_now", 0, self.horloge)
        db.execute("PRAGMA secure_delete=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def _importer(self, ancien):
        if not ancien or not Path(ancien).exists():
            return []
        try:
            data = json.loads(Path(ancien).read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict):
                raise ValueError()
            data.setdefault("facts", data.get("faits", []))
            resultat = []
            for cat in CATEGORIES:
                valeurs = data.get(cat, [] if cat == "facts" else {})
                if not isinstance(valeurs, list if cat == "facts" else dict):
                    raise ValueError()
                items = (("", v) for v in valeurs) if cat == "facts" else valeurs.items()
                for cle, contenu in items:
                    resultat.append(dict(id=secrets.token_hex(12), categorie=cat,
                                         cle=str(cle), contenu=str(contenu)))
            return resultat
        except (ValueError, OSError):
            raise ErreurMemoire("Ancienne mémoire illisible : migration interrompue, fichier préservé.") from None

    def _zone(self, db, identifiant):
        if not isinstance(identifiant, str) or len(identifiant) > 128:
            raise ErreurMemoire("Identifiant de zone invalide.")
        row = db.execute("SELECT * FROM zones WHERE id=?", (identifiant,)).fetchone()
        if row is None:
            raise ErreurMemoire("Zone introuvable.")
        return dict(row)

    def _periode(self, zone):
        now = self.horloge()
        return ((zone["debut"] is None or now >= zone["debut"])
                and (zone["fin"] is None or now < zone["fin"]))

    def _entete(self, zone):
        try:
            return json.loads(zone["crypto"]) if zone.get("crypto") else None
        except (ValueError, TypeError):
            raise ErreurMemoire(ERREUR_AUTH) from None

    def _acces(self, zone):
        if not zone.get("crypto"):
            return
        session = self.sessions.get(zone["id"])
        if not session or session[0] <= self.horloge() or session[1] != zone["crypto"] or not self.crypto.ouverte(zone["id"]):
            self.bloquer(zone["id"])
            raise ErreurMemoire("Déverrouille d'abord cette zone, à la voix ou dans le panneau.")

    def _lire(self, zone, periode=True):
        if periode and not self._periode(zone):
            raise ErreurMemoire("Cette zone est en dehors de sa période d'accès.")
        self._acces(zone)
        try:
            donnees = json.loads(zone["donnees"])
            resultat=[]
            for e in donnees:
                expire=e.get("expiration")
                if expire is not None and expire <= self.horloge():
                    continue
                if zone.get("crypto"):
                    e=self.crypto.dechiffrer(zone["id"], e["id"], e, extra={"expiration":expire})
                resultat.append(e)
            return resultat
        except (ErreurCrypto, ValueError, TypeError, KeyError):
            raise ErreurMemoire(ERREUR_AUTH) from None

    def _encoder(self, zone, entrees, coffre=None):
        if zone.get("crypto"):
            c=coffre or self.crypto
            donnees=[]
            for e in entrees:
                expire=e.get("expiration")
                chiffre=c.chiffrer(zone["id"], e["id"], e, extra={"expiration":expire})
                chiffre["expiration"]=expire
                donnees.append(chiffre)
        else:
            donnees=entrees
        return json.dumps(donnees,ensure_ascii=False)

    def _notifier(self):
        self.generation += 1
        for rappel in tuple(self.observateurs):
            try:
                rappel()
            except Exception:
                pass  # Pas de journalisation d'une exception pouvant contenir du texte privé.

    def bloquer(self, identifiant):
        with self.verrou:
            if not isinstance(identifiant, str):
                raise ErreurMemoire("Identifiant de zone invalide.")
            ouvert=self.crypto.ouverte(identifiant) or identifiant in self.sessions
            self.crypto.verrouiller(identifiant)
            self.sessions.pop(identifiant, None)
            self.propositions={k:p for k,p in self.propositions.items() if p["zone"]["id"]!=identifiant}
            if ouvert:
                self._notifier()

    def _journal_entete(self, db):
        row=db.execute("SELECT valeur FROM metadata WHERE cle='historique_crypto'").fetchone()
        return json.loads(row[0]) if row else None

    def _zone_journal(self, db):
        entete=self._journal_entete(db)
        if not entete:
            raise ErreurMemoire("Définis d'abord le mot de passe de l'historique dans le panneau Mémoire.")
        return dict(id="_historique", crypto=json.dumps(entete,sort_keys=True), debut=None, fin=None)

    def acces_historique(self):
        with self.verrou,self._connexion() as db:
            entete=self._journal_entete(db)
            ouvert=False
            if entete:
                try:
                    self._acces(self._zone_journal(db));ouvert=True
                except ErreurMemoire:
                    pass
            return dict(initialise=bool(entete), ouvert=ouvert,
                        session_fin=self.sessions.get("_historique",(None,))[0])

    def debloquer(self, identifiant, mot_de_passe):
        with self.verrou, self._connexion() as db:
            zone=self._zone_journal(db) if identifiant=="_historique" else self._zone(db,identifiant)
            entete=self._entete(zone)
            if not entete:
                raise ErreurMemoire("Cette zone n'a pas de mot de passe.")
            row=db.execute('SELECT nombre,attente FROM acces_echecs WHERE zone=?',(identifiant,)).fetchone()
            nombre,attente=tuple(row) if row else (0,0)
            if attente > self.horloge():
                raise ErreurMemoire("Trop d'essais. Réessaie dans une minute.")
            self.bloquer(identifiant)
            erreur=False
            try:
                if entete.get('cryptoVersion')==0:
                    if entete.get('algorithm')!='legacy-aes256-gcm-scrypt':
                        raise ErreurCrypto()
                    from core.memoire_crypto_legacy import lire_ancien
                    entrees=lire_ancien(identifiant,zone['sel'],zone['donnees'],mot_de_passe)
                    with self._temporaire() as c:
                        nouveau=c.creer(identifiant,mot_de_passe,self.kdf)
                        zone['crypto']=json.dumps(nouveau,sort_keys=True)
                        donnees=self._encoder(zone,entrees,c)
                    # L'ancien format reste intact si l'écriture échoue.
                    db.execute('UPDATE zones SET crypto=?,sel=NULL,donnees=?,revision=revision+1 WHERE id=?',
                               (zone['crypto'],donnees,identifiant))
                    entete=nouveau
                self.crypto.deverrouiller(identifiant,entete,mot_de_passe)
            except (ErreurCrypto, TypeError, ValueError):
                nombre += 1
                delai=min(900,60*2**min(4,max(0,nombre-5))) if nombre>=5 else 0
                db.execute('INSERT OR REPLACE INTO acces_echecs VALUES (?,?,?)',
                           (identifiant,nombre,self.horloge()+delai))
                erreur=True
            if not erreur:
                db.execute('DELETE FROM acces_echecs WHERE zone=?',(identifiant,))
                self.sessions[identifiant]=(self.horloge()+self.duree_session,zone['crypto'])
                self._notifier()
        if erreur:
            raise ErreurMemoire(ERREUR_AUTH)
        return "Accès déverrouillé pour cette session."

    @contextmanager
    def _temporaire(self):
        c=Coffre()
        try:
            yield c
        finally:
            c.fermer()

    def consulter(self, identifiant, requete=""):
        with self.verrou,self._connexion() as db:
            entrees=self._lire(self._zone(db,identifiant))
            besoin=normaliser(requete).strip()
            return [e for e in entrees if not besoin or besoin in normaliser(e['cle']+' '+e['contenu'])]

    def liste_zones(self):
        with self.verrou,self._connexion() as db:
            return [dict(id=r['id'],nom=r['nom'],debut=r['debut'],fin=r['fin'],protegee=bool(r['crypto']))
                    for r in db.execute('SELECT id,nom,debut,fin,crypto FROM zones ORDER BY nom')]

    def _changer_secret(self, zone, entete, ancien, nouveau):
        if nouveau is not None and (not isinstance(nouveau,str) or not 8<=len(nouveau)<=1024):
            raise ErreurMemoire("Choisis un mot de passe d'au moins huit caractères.")
        with self._connexion() as db:
            row=db.execute('SELECT nombre,attente FROM acces_echecs WHERE zone=?',(zone,)).fetchone()
            nombre,attente=tuple(row) if row else (0,0)
            if attente>self.horloge():
                raise ErreurMemoire("Trop d'essais. Réessaie dans une minute.")
            try:
                resultat=(self.crypto.verifier_mot_de_passe(zone,entete,ancien) if nouveau is None else
                          self.crypto.changer_mot_de_passe(zone,entete,ancien,nouveau,self.kdf))
                db.execute('DELETE FROM acces_echecs WHERE zone=?',(zone,))
                erreur=False
            except ErreurCrypto:
                nombre+=1
                db.execute('INSERT OR REPLACE INTO acces_echecs VALUES (?,?,?)',
                    (zone,nombre,self.horloge()+(min(900,60*2**min(4,max(0,nombre-5))) if nombre>=5 else 0)))
                erreur=True
        if erreur:
            raise ErreurMemoire(ERREUR_AUTH)
        return resultat

    def etat(self):
        with self.verrou, self._connexion() as db:
            zones = []
            for row in db.execute("SELECT * FROM zones ORDER BY nom"):
                z = dict(row)
                accessible, entrees, raison = False, [], ""
                try:
                    entrees = self._lire(z)
                    accessible = True
                except ErreurMemoire as e:
                    raison = str(e)
                zones.append(dict(id=z["id"], nom=z["nom"], debut=z["debut"], fin=z["fin"],
                                  protegee=bool(z.get("crypto")), accessible=accessible, raison=raison,
                                  revision=z["revision"], entrees=entrees,
                                  session_fin=self.sessions.get(z["id"], (None, None))[0]))
            return {"zones": zones, "maintenant": self.horloge(), "retention_secondes": SEPT_JOURS, "generation": self.generation, "historique_acces":self.acces_historique()}

    def contexte(self, protegees=False):
        """Aucune zone conditionnelle dans un contexte de modèle, même après déverrouillage."""
        with self.verrou,self._connexion() as db:
            zones=[]
            for row in db.execute("SELECT * FROM zones WHERE id='generale' AND crypto IS NULL AND debut IS NULL AND fin IS NULL"):
                z=dict(row)
                z.update(entrees=self._lire(z),session_fin=None)
                zones.append(z)
        signature = tuple((z["id"], z["revision"], z["session_fin"]) for z in zones)
        m = {"preferences": {}, "people": {}, "projects": {}, "facts": []}
        for zone in zones:
            for e in zone["entrees"]:
                if e["categorie"] == "facts":
                    m["facts"].append(e["contenu"])
                else:
                    cle = e["cle"] if zone["id"] == "generale" else f'{zone["nom"]} / {e["cle"]}'
                    m[e["categorie"]][cle] = e["contenu"]
        return signature, m

    def preparer(self, action, valeurs, origine="panneau"):
        """Construit une proposition figée, sans écriture sur disque."""
        if origine not in ("panneau", "voix") or not isinstance(valeurs, dict) or not isinstance(action, str):
            raise ErreurMemoire("Proposition invalide.")
        with self.verrou, self._connexion() as db:
            maintenant = self.horloge()
            self.propositions = {k: p for k, p in self.propositions.items() if p["expire"] > maintenant}
            if len(self.propositions) >= 50:
                raise ErreurMemoire("Trop de propositions en attente.")
            v = copy.deepcopy(valeurs)
            if action.startswith('historique_'):
                return self._preparer_journal(action,v,origine)
            self._zone_journal(db)  # Aucune nouvelle écriture avant initialisation du journal chiffré.
            creation = action == "zone_creer"
            zone = (dict(id=secrets.token_hex(12), nom="", debut=None, fin=None, sel=None,
                         donnees="[]", revision=0, crypto=None) if creation else
                    self._zone(db, v.get("zone", "generale")))
            revision = zone["revision"]
            ancien = copy.deepcopy(zone)
            ids = []
            if action in ("zone_creer", "zone_modifier"):
                if zone["id"] == "generale":
                    raise ErreurMemoire("Crée une zone dédiée pour définir des conditions d'accès.")
                if not creation and zone.get('crypto') and v.get('mot_de_passe_action','garder')=='garder':
                    self._changer_secret(zone['id'],self._entete(zone),v.get('ancien_mot_de_passe',''),None)
                zone["nom"] = _texte(v.get("nom"), 80)
                zone["debut"], zone["fin"] = date_utc(v.get("debut")), date_utc(v.get("fin"))
                if zone["debut"] is not None and zone["fin"] is not None and zone["debut"] >= zone["fin"]:
                    raise ErreurMemoire("La fin doit être postérieure au début.")
                mode=v.get('mot_de_passe_action','garder')
                if mode not in ('garder','definir'):
                    raise ErreurMemoire("Le chiffrement ne peut pas être retiré. Il est possible de changer le mot de passe ou de supprimer la zone.")
                if mode=='definir':
                    try:
                        if zone.get('crypto'):
                            entete=self._changer_secret(zone['id'],self._entete(zone),
                                v.get('ancien_mot_de_passe',''),v.get('mot_de_passe',''))
                            zone['crypto']=json.dumps(entete,sort_keys=True)
                            # IMPORTANT : zone['donnees'] inchangé octet pour octet.
                        else:
                            entrees=[] if creation else self._lire(ancien,periode=False)
                            with self._temporaire() as c:
                                entete=c.creer(zone['id'],v.get('mot_de_passe',''),self.kdf)
                                zone['crypto']=json.dumps(entete,sort_keys=True)
                                zone['donnees']=self._encoder(zone,entrees,c)
                    except ValueError as e:
                        raise ErreurMemoire(str(e)) from None
                # Le mot de passe lui-même n'est jamais conservé dans la proposition.
                detail = {k: zone[k] for k in ("nom", "debut", "fin")}
                detail["mot_de_passe"] = "défini" if zone.get("crypto") else "absent"
                resume = ("Créer" if creation else "Modifier") + f' la zone « {zone["nom"]} ».'
            elif action == "zone_supprimer":
                if zone["id"] == "generale":
                    raise ErreurMemoire("La zone générale ne peut pas être supprimée.")
                self._acces(zone)  # Mot de passe obligatoire même si les dates ont expiré.
                resume = f'Supprimer la zone « {zone["nom"]} » et tout son contenu.'
                detail = {"zone": zone["nom"]}
            elif action in ("ajouter", "modifier", "supprimer", "oublier"):
                entrees = self._lire(zone)
                if action in ("ajouter", "modifier"):
                    cat = v.get("categorie", "facts")
                    if cat not in CATEGORIES:
                        raise ErreurMemoire("Catégorie inconnue.")
                    contenu = _texte(v.get("contenu"))
                    etiquette = str(v.get("cle", "")).strip()[:100]
                    if cat != "facts" and not etiquette:
                        etiquette = contenu[:40]
                    cible = next((e for e in entrees if e["id"] == v.get("id")), None)
                    if action == "modifier" and cible is None:
                        raise ErreurMemoire("Information introuvable.")
                    if action == "ajouter":
                        cible = next((e for e in entrees if e["categorie"] == cat and
                                      ((cat != "facts" and e["cle"] == etiquette) or
                                       (cat == "facts" and e["contenu"] == contenu))), None)
                    if cat != "facts" and any(e is not cible and e["categorie"] == cat and
                                               e["cle"] == etiquette for e in entrees):
                        raise ErreurMemoire("Cette étiquette existe déjà dans la zone. Choisis-en une autre.")
                    avant = copy.deepcopy(cible)
                    if cible is None:
                        cible = {"id": secrets.token_hex(12)}
                        entrees.append(cible)
                    else:
                        action = "modifier"
                    expiration=date_utc(v.get('expiration',cible.get('expiration')))
                    if expiration is not None and expiration<=self.horloge():
                        raise ErreurMemoire("La suppression programmée doit être dans le futur.")
                    cible.update(categorie=cat, cle=etiquette, contenu=contenu, expiration=expiration)
                    ids = [cible["id"]]
                    detail = {"avant": avant, "apres": copy.deepcopy(cible)}
                    resume = ("Modifier" if avant else "Retenir") + f' dans « {zone["nom"]} » : {contenu}'
                    if avant:
                        resume = f'Remplacer « {avant["contenu"]} » par « {contenu} » dans « {zone["nom"]} ».'
                    if expiration is not None:
                        resume += ' Suppression programmée le ' + datetime.fromtimestamp(expiration,timezone.utc).isoformat() + '.'
                    elif avant and avant.get('expiration') is not None:
                        resume += ' Retirer sa suppression programmée et conserver ce souvenir sans limite.'
                else:
                    besoin = normaliser(_texte(v.get("sujet"))) if action == "oublier" else ""
                    cibles = [e for e in entrees if
                              (besoin in normaliser(e["cle"] + " " + e["contenu"]) if besoin
                               else e["id"] == v.get("id"))]
                    if not cibles:
                        raise ErreurMemoire("Aucune information correspondante dans cette zone.")
                    ids = [e["id"] for e in cibles]
                    detail = {"supprimer": cibles}
                    resume = "Oublier dans « " + zone["nom"] + " » : " + " ; ".join(e["contenu"] for e in cibles)
                    entrees = [e for e in entrees if e["id"] not in ids]
                    action = "supprimer"
                zone["donnees"] = self._encoder(zone, entrees)
            else:
                raise ErreurMemoire("Action de mémoire inconnue.")
            jeton = secrets.token_urlsafe(32)
            self.propositions[jeton] = dict(action=action, zone=zone, ancien=ancien,
                                            revision=revision, origine=origine, ids=ids,
                                            expire=maintenant + 300)
            return dict(jeton=jeton, resume=resume, detail=detail, expire=maintenant + 300)

    def annuler(self, jeton, origine="panneau"):
        with self.verrou:
            if not isinstance(jeton, str):
                raise ErreurMemoire("Validation invalide.")
            p = self.propositions.get(jeton)
            if p and p["origine"] == origine:
                self.propositions.pop(jeton)

    def confirmer(self, jeton, origine="panneau"):
        with self.verrou, self._connexion() as db:
            if not isinstance(jeton, str):
                raise ErreurMemoire("Validation invalide.")
            p = self.propositions.get(jeton)
            if not p or p["origine"] != origine:
                raise ErreurMemoire("Validation absente ou déjà utilisée.")
            self.propositions.pop(jeton)
            if self.horloge() >= p["expire"]:
                raise ErreurMemoire("Proposition expirée. Prépare de nouveau le changement.")
            db.execute("BEGIN IMMEDIATE")
            if p['action'].startswith('historique_'):
                return self._confirmer_journal(db,p)
            zone = p["zone"]
            if p["revision"]:
                actuelle = self._zone(db, zone["id"])
                if actuelle["revision"] != p["revision"]:
                    raise ErreurMemoire("La zone a changé. Vérifie une nouvelle proposition.")
                if p['action']!='zone_modifier':
                    self._acces(actuelle)
                if p["action"] in ("ajouter", "modifier", "supprimer") and not self._periode(actuelle):
                    raise ErreurMemoire("La période d'accès à cette zone est terminée.")
            if p["action"] == "zone_supprimer":
                db.execute("DELETE FROM zones WHERE id=?", (zone["id"],))
            else:
                db.execute("INSERT OR REPLACE INTO zones(id,nom,debut,fin,sel,donnees,revision,crypto) VALUES (?,?,?,?,?,?,?,?)",
                           (zone["id"], zone["nom"], zone["debut"], zone["fin"], None,
                            zone["donnees"], p["revision"] + 1, zone.get('crypto')))
            if p["action"].startswith("zone_"):
                self.bloquer(zone["id"])
            evenement = dict(action=p["action"], zone=zone["nom"], zone_id=zone["id"],
                              elements=p["ids"], origine=origine)
            self._journaliser(db,evenement)
            self._notifier()
            self.reveil.set()
            return "C'est fait, Monsieur. La mémoire a été mise à jour."

    def _preparer_journal(self,action,v,origine):
        with self._connexion() as db:
            actuel=self._journal_entete(db)
        try:
            if action=='historique_initialiser' and not actuel:
                with self._temporaire() as c:
                    entete=c.creer_journal(v.get('mot_de_passe',''),self.kdf)
                resume="Protéger l'historique avec ce mot de passe, sans possibilité de récupération."
            elif action=='historique_mot_de_passe' and actuel:
                entete=dict(actuel)
                entete.update(self._changer_secret('_historique',actuel,
                    v.get('ancien_mot_de_passe',''),v.get('mot_de_passe','')))
                resume="Remplacer le mot de passe de l'historique, sans possibilité de récupération."
            else:
                raise ErreurMemoire("Cette action n'est pas disponible pour l'historique.")
        except ValueError as e:
            raise ErreurMemoire(str(e)) from None
        jeton=secrets.token_urlsafe(32)
        self.propositions[jeton]=dict(action=action,zone={'id':'_historique'},entete=entete,ancien=actuel,
                                      expire=self.horloge()+300,origine=origine)
        return dict(jeton=jeton,resume=resume,detail={},expire=self.horloge()+300)

    def _confirmer_journal(self,db,p):
        if self._journal_entete(db)!=p['ancien']:
            raise ErreurMemoire("L'historique a changé. Prépare une nouvelle validation.")
        entete=p['entete']
        db.execute("INSERT OR REPLACE INTO metadata VALUES ('historique_crypto',?)",
                   (json.dumps(entete,sort_keys=True),))
        if p['action']=='historique_initialiser':
            for r in db.execute('SELECT * FROM historique WHERE expire > ?',(self.horloge(),)).fetchall():
                self._journaliser(db,json.loads(r['evenement']),cree=r['cree'])
            # Migration de représentation atomique, sans changer les événements ou leur échéance.
            db.execute('DROP TRIGGER IF EXISTS historique_retention')
            db.execute('DELETE FROM historique')
            db.execute("""CREATE TRIGGER historique_retention BEFORE DELETE ON historique
                WHEN OLD.expire > red_now() BEGIN SELECT RAISE(ABORT,'Retention de sept jours'); END""")
        else:
            self._journaliser(db,dict(action='historique_mot_de_passe',zone='Historique',elements=[],origine=p['origine']))
        self.bloquer('_historique')
        self._notifier()
        return "L'historique est protégé. Son mot de passe est nécessaire pour le consulter."

    def _journaliser(self,db,evenement,cree=None):
        entete=self._journal_entete(db)
        if not entete:
            raise ErreurMemoire("Définis d'abord le mot de passe de l'historique.")
        now=self.horloge() if cree is None else cree
        identifiant=secrets.token_hex(16)
        chiffre=Coffre.deposer_evenement(entete,identifiant,evenement,now,now+SEPT_JOURS)
        db.execute('INSERT INTO historique_chiffre VALUES (?,?,?,?)',
                   (identifiant,now,now+SEPT_JOURS,json.dumps(chiffre)))

    def historique(self):
        self.purger()
        with self.verrou,self._connexion() as db:
            self._acces(self._zone_journal(db))
            entete=self._journal_entete(db)
            resultat=[]
            try:
                for r in db.execute('SELECT * FROM historique_chiffre WHERE expire>? ORDER BY cree DESC,rowid DESC',(self.horloge(),)):
                    e=self.crypto.lire_evenement(entete,r['id'],json.loads(r['evenement']),r['cree'],r['expire'])
                    resultat.append(dict(id=r['id'],cree=r['cree'],expire=r['expire'],**e))
            except ErreurCrypto:
                raise ErreurMemoire(ERREUR_AUTH) from None
            return resultat

    def purger(self):
        with self.verrou,self._connexion() as db:
            now=self.horloge()
            db.execute('DELETE FROM historique WHERE expire<=?',(now,))
            db.execute('DELETE FROM historique_chiffre WHERE expire<=?',(now,))
            self.propositions={k:p for k,p in self.propositions.items() if p['expire']>now}
            for ident,(expiration,_) in list(self.sessions.items()):
                if expiration<=now:
                    self.bloquer(ident)
            # Seules les suppressions explicitement programmées lors d'une validation sont automatiques.
            for row in db.execute('SELECT * FROM zones').fetchall():
                z=dict(row)
                if not self._periode(z) and z['id'] in self.sessions:
                    self.bloquer(z['id'])
                if self._entete(z) and self._entete(z).get('cryptoVersion')==0:
                    continue
                entries=json.loads(z['donnees'])
                expires=[e for e in entries if e.get('expiration') is not None and e['expiration']<=now]
                if expires:
                    restants=[e for e in entries if e not in expires]
                    self._journaliser(db,dict(action='expiration',zone=z['nom'],zone_id=z['id'],elements=[e['id'] for e in expires],origine='expiration_validée'))
                    db.execute('UPDATE zones SET donnees=?,revision=revision+1 WHERE id=?',
                               (json.dumps(restants,ensure_ascii=False),z['id']))
                    self._notifier()

    def demarrer(self):
        with self.verrou:
            if self.fil and self.fil.is_alive():
                return
            self.arret.clear()

            def boucle():
                import logging
                while not self.arret.is_set():
                    self.reveil.clear()
                    attente = 1.0
                    try:
                        self.purger()
                        with self._connexion() as db:
                            prochaine = db.execute("SELECT MIN(expire) FROM historique_chiffre").fetchone()[0]
                        if prochaine is not None:
                            attente = max(.01, min(1.0, prochaine - self.horloge()))
                    except Exception:
                        logging.getLogger("red.memoire").error("Purge de mémoire indisponible.")
                    self.reveil.wait(attente)
            self.fil = threading.Thread(target=boucle, name="red-memoire-retention", daemon=True)
            self.fil.start()

    def fermer(self):
        self.arret.set()
        self.reveil.set()
        if self.fil:
            self.fil.join(timeout=2)
        with self.verrou:
            self.crypto.fermer()
            self.sessions.clear()
            self.propositions.clear()
