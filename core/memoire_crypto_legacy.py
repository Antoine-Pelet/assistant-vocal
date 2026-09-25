"""Lecture uniquement du format AES/scrypt précédent pour migration atomique."""
import base64
import json
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from nacl._sodium import ffi, lib
from core.memoire_crypto import ErreurCrypto


def lire_ancien(zone, sel, donnees, mot):
    cle = bytearray()
    mot_octets = bytearray(mot, 'utf-8')
    try:
        cle.extend(Scrypt(salt=base64.b64decode(sel,validate=True),length=32,n=2**15,r=8,p=1).derive(mot_octets))
        brut=base64.b64decode(donnees,validate=True)
        return json.loads(AESGCM(cle).decrypt(brut[:12],brut[12:],zone.encode()))
    except Exception:
        raise ErreurCrypto() from None
    finally:
        for tampon in (cle,mot_octets):
            if tampon:lib.sodium_memzero(ffi.from_buffer(tampon),len(tampon))
