"""Cryptographie isolée : primitives libsodium, DEK par zone et KEK Argon2id.

Les buffers de clés restent dans cette couche. Les structures retournées ne
contiennent que des ciphertexts et des paramètres publics versionnés.
"""
import base64
import json
from contextlib import contextmanager

from nacl import bindings, utils
from nacl._sodium import ffi, lib

VERSION = 1
ALGORITHME = "xchacha20-poly1305-ietf"
ERREUR_AUTH = "Mot de passe incorrect ou données invalides."
DEFAUT_KDF = dict(algorithm="argon2id", algorithmVersion=19,
                  memoryCost=131072, timeCost=3, parallelism=1)


class ErreurCrypto(ValueError):
    def __init__(self):
        super().__init__(ERREUR_AUTH)


def canonique(objet):
    return json.dumps(objet, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def b64(brut):
    return base64.b64encode(brut).decode("ascii")


def deb64(texte, taille=None):
    try:
        brut = base64.b64decode(texte, validate=True)
        if taille is not None and len(brut) != taille:
            raise ValueError()
        return brut
    except (ValueError, TypeError):
        raise ErreurCrypto() from None


class _Secret:
    """Buffer C nettoyé par sodium_memzero, verrouillé en RAM si l'OS l'autorise."""
    def __init__(self, taille=32):
        self.taille = taille
        self.ptr = ffi.new("unsigned char[]", max(taille, 1))
        self.verrouille = lib.sodium_mlock(self.ptr, max(taille, 1)) == 0
        self.ferme = False

    def fermer(self):
        if not self.ferme:
            lib.sodium_memzero(self.ptr, max(self.taille, 1))
            if self.verrouille:
                lib.sodium_munlock(self.ptr, max(self.taille, 1))
            self.ferme = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.fermer()

    def __del__(self):
        self.fermer()


@contextmanager
def _octets_secret(valeur):
    if not isinstance(valeur, str) or len(valeur) > 1024:
        raise ErreurCrypto()
    # Les chaînes Python/JSON/STT d'entrée ne sont pas effaçables de façon garantie.
    # Le buffer UTF-8 mutable utilisé par la KDF est explicitement nettoyé.
    brut = bytearray(valeur, "utf-8")
    try:
        yield ffi.from_buffer("unsigned char[]", brut), len(brut)
    finally:
        if brut:
            lib.sodium_memzero(ffi.from_buffer(brut), len(brut))


def parametres(valeurs=None):
    p = dict(DEFAUT_KDF)
    if valeurs is not None:
        if not isinstance(valeurs, dict):
            raise ErreurCrypto()
        p.update({k: valeurs[k] for k in DEFAUT_KDF if k in valeurs})
    if (p["algorithm"] != "argon2id" or p["algorithmVersion"] != 19 or
        p["parallelism"] != 1 or not isinstance(p["memoryCost"], int) or
        not isinstance(p["timeCost"], int) or not 65536 <= p["memoryCost"] <= 524288 or
        not 2 <= p["timeCost"] <= 10):
        raise ErreurCrypto()
    return p


def _deriver(mot, sel, p):
    p = parametres(p)
    cle = _Secret()
    try:
        with _octets_secret(mot) as (pwd, longueur):
            rc = lib.crypto_pwhash(cle.ptr, 32, ffi.cast("char *", pwd), longueur,
                sel, p["timeCost"], p["memoryCost"] * 1024,
                bindings.crypto_pwhash_ALG_ARGON2ID13)
        if rc != 0:
            raise ErreurCrypto()
        return cle
    except Exception:
        cle.fermer()
        raise


def _aleatoire():
    cle = _Secret()
    lib.randombytes(cle.ptr, 32)
    return cle


def _aad(zone, objet, type_objet, extra=None):
    return canonique(dict(schemaVersion=VERSION, zoneId=zone, memoryId=objet,
                          objectType=type_objet, metadata=extra or {}))


def _chiffrer(cle, message, longueur, aad):
    if cle.ferme:
        raise ErreurCrypto()
    nonce = utils.random(24)
    sortie = ffi.new("unsigned char[]", longueur + 16)
    taille = ffi.new("unsigned long long *")
    rc = lib.crypto_aead_xchacha20poly1305_ietf_encrypt(
        sortie, taille, message, longueur, aad, len(aad), ffi.NULL, nonce, cle.ptr)
    if rc:
        raise ErreurCrypto()
    return dict(algorithm=ALGORITHME, nonce=b64(nonce),
                ciphertext=b64(ffi.buffer(sortie, taille[0])))


def _dechiffrer(cle, enveloppe, aad):
    if cle.ferme or not isinstance(enveloppe, dict) or enveloppe.get("algorithm") != ALGORITHME:
        raise ErreurCrypto()
    nonce = deb64(enveloppe.get("nonce"), 24)
    chiffre = deb64(enveloppe.get("ciphertext"))
    if len(chiffre) < 16 or len(chiffre) > 16 * 1024 * 1024:
        raise ErreurCrypto()
    sortie = _Secret(len(chiffre) - 16)
    taille = ffi.new("unsigned long long *")
    if lib.crypto_aead_xchacha20poly1305_ietf_decrypt(
            sortie.ptr, taille, ffi.NULL, chiffre, len(chiffre), aad, len(aad), nonce, cle.ptr):
        sortie.fermer()
        raise ErreurCrypto()
    return sortie


def _ouvrir_cle(zone, entete, mot):
    try:
        if entete.get("cryptoVersion") != VERSION:
            raise ErreurCrypto()
        kdf = entete["kdf"]
        p = parametres(kdf)
        sel = deb64(kdf["salt"], 16)
        with _deriver(mot, sel, p) as kek:
            dek = _dechiffrer(kek, entete["wrappedKey"], _aad(zone, "zoneKey", "wrappedKey", kdf))
        if dek.taille != 32:
            dek.fermer()
            raise ErreurCrypto()
        return dek
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ErreurCrypto() from None


def _envelopper(zone, dek, mot, params):
    if not isinstance(mot, str) or not 8 <= len(mot) <= 1024:
        raise ValueError("Choisis un mot de passe d'au moins huit caractères.")
    kdf = dict(parametres(params), salt=b64(utils.random(16)))
    with _deriver(mot, deb64(kdf["salt"], 16), kdf) as kek:
        enveloppe = _chiffrer(kek, dek.ptr, 32, _aad(zone, "zoneKey", "wrappedKey", kdf))
    return dict(cryptoVersion=VERSION, kdf=kdf, wrappedKey=enveloppe)


class Coffre:
    """API de zones ; aucun appelant ne reçoit une clé déchiffrée."""
    def __init__(self):
        self._cles = {}

    def creer(self, zone, mot, params=None):
        self.verrouiller(zone)
        dek = _aleatoire()
        try:
            entete = _envelopper(zone, dek, mot, params)
            self._cles[zone] = dek
            return entete
        except Exception:
            dek.fermer()
            raise

    def deverrouiller(self, zone, entete, mot):
        self.verrouiller(zone)
        self._cles[zone] = _ouvrir_cle(zone, entete, mot)

    def ouverte(self, zone):
        return zone in self._cles and not self._cles[zone].ferme

    def _cle(self, zone):
        if not self.ouverte(zone):
            raise ErreurCrypto()
        return self._cles[zone]

    def verrouiller(self, zone):
        cle = self._cles.pop(zone, None)
        if cle:
            cle.fermer()

    def fermer(self):
        for zone in list(self._cles):
            self.verrouiller(zone)

    def changer_mot_de_passe(self, zone, entete, ancien, nouveau, params=None):
        # Réauthentification obligatoire ; la clé active en session ne suffit pas.
        with _ouvrir_cle(zone, entete, ancien) as dek:
            return _envelopper(zone, dek, nouveau, params)

    def verifier_mot_de_passe(self, zone, entete, mot):
        with _ouvrir_cle(zone,entete,mot):
            return True

    def chiffrer(self, zone, identifiant, contenu, type_objet="memory", extra=None):
        brut = bytearray(canonique(contenu))
        try:
            chiffre = _chiffrer(self._cle(zone), ffi.from_buffer(brut), len(brut),
                               _aad(zone, identifiant, type_objet, extra))
            return dict(id=identifiant, zoneId=zone, cryptoVersion=VERSION, encryption=chiffre)
        finally:
            if brut:
                lib.sodium_memzero(ffi.from_buffer(brut), len(brut))

    def dechiffrer(self, zone, identifiant, enregistrement, type_objet="memory", extra=None):
        try:
            if (enregistrement["id"] != identifiant or enregistrement["zoneId"] != zone or
                enregistrement["cryptoVersion"] != VERSION):
                raise ErreurCrypto()
            with _dechiffrer(self._cle(zone), enregistrement["encryption"],
                            _aad(zone, identifiant, type_objet, extra)) as clair:
                return json.loads(ffi.buffer(clair.ptr, clair.taille)[:])
        except (KeyError, TypeError, ValueError):
            raise ErreurCrypto() from None

    def creer_journal(self, mot, params=None):
        """Clé privée de dépôt protégée par la DEK ; seule la clé publique reste accessible."""
        entete = self.creer("_historique", mot, params)
        public = ffi.new("unsigned char[]", 32)
        with _Secret() as prive:
            if lib.crypto_box_keypair(public, prive.ptr):
                raise ErreurCrypto()
            entete["publicKey"] = b64(ffi.buffer(public, 32))
            entete["privateKey"] = _chiffrer(self._cle("_historique"), prive.ptr, 32,
                _aad("_historique", "privateKey", "historyPrivateKey", {"publicKey": entete["publicKey"]}))
        return entete

    @staticmethod
    def deposer_evenement(entete, identifiant, contenu, cree, expire):
        """Chiffre un événement même journal verrouillé, sans conserver de clé privée."""
        aad = _aad("_historique", identifiant, "historyEvent", dict(cree=cree, expire=expire))
        public = deb64(entete.get("publicKey"), 32)
        brut = bytearray(canonique(contenu))
        try:
            with _aleatoire() as cle:
                chiffre = _chiffrer(cle, ffi.from_buffer(brut), len(brut), aad)
                scelle = ffi.new("unsigned char[]", 32 + bindings.crypto_box_SEALBYTES)
                if lib.crypto_box_seal(scelle, cle.ptr, 32, public):
                    raise ErreurCrypto()
                return dict(cryptoVersion=VERSION, encryption=chiffre,
                            sealedKey=b64(ffi.buffer(scelle)), keyAlgorithm="libsodium-sealedbox")
        finally:
            if brut:
                lib.sodium_memzero(ffi.from_buffer(brut), len(brut))

    def lire_evenement(self, entete, identifiant, donnees, cree, expire):
        try:
            if donnees["cryptoVersion"] != VERSION or donnees["keyAlgorithm"] != "libsodium-sealedbox":
                raise ErreurCrypto()
            public = deb64(entete["publicKey"], 32)
            scelle = deb64(donnees["sealedKey"], 32 + bindings.crypto_box_SEALBYTES)
            with _dechiffrer(self._cle("_historique"), entete["privateKey"], _aad(
                    "_historique", "privateKey", "historyPrivateKey", {"publicKey": entete["publicKey"]})) as prive, _Secret() as cle:
                if prive.taille != 32:
                    raise ErreurCrypto()
                if lib.crypto_box_seal_open(cle.ptr, scelle, len(scelle), public, prive.ptr):
                    raise ErreurCrypto()
                with _dechiffrer(cle, donnees["encryption"], _aad("_historique", identifiant,
                                "historyEvent", dict(cree=cree, expire=expire))) as clair:
                    return json.loads(ffi.buffer(clair.ptr, clair.taille)[:])
        except (TypeError, KeyError, ValueError):
            raise ErreurCrypto() from None
