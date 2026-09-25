"""Catalogue de voix locales. Les identifiants publics ne sont pas des chemins."""
from pathlib import Path

from core.config import reglage

RACINE = Path(__file__).resolve().parent.parent
PROFILS = {
    "siwis_fr": {
        "nom": "Siwis — français", "description": "Voix féminine naturelle.",
        "modele": "voix/fr_FR-siwis-medium.onnx", "effet": None,
    },
    "tom_fr": {
        "nom": "Tom — français", "description": "Voix masculine naturelle.",
        "modele": "voix/fr_FR-tom-medium.onnx", "effet": None,
    },
    "jarvis_fr": {
        "nom": "Red — style français",
        "description": "Voix masculine grave, avec un léger effet synthétique. Style calme et posé de Red.",
        "modele": "voix/fr_FR-tom-medium.onnx", "effet": "jarvis",
    },
}


def selection():
    identifiant = reglage("tts.voix_locale", "")
    if identifiant in PROFILS:
        return identifiant
    chemin = str(reglage("piper.modele", "") or "").replace("\\", "/")
    for identifiant in ("siwis_fr", "tom_fr"):
        if chemin.endswith(PROFILS[identifiant]["modele"].split("/")[-1]):
            return identifiant
    return ""


def installee(identifiant):
    profil = PROFILS.get(identifiant)
    if not profil:
        return False
    chemin = RACINE / profil["modele"]
    return chemin.is_file() and chemin.with_suffix(".onnx.json").is_file()


def catalogue():
    active = selection()
    return [{"id": identifiant, "nom": p["nom"], "description": p["description"],
             "installee": installee(identifiant), "active": identifiant == active}
            for identifiant, p in PROFILS.items()]


def appliquer_effet(audio, frequence, identifiant):
    if PROFILS.get(identifiant, {}).get("effet") != "jarvis":
        return audio, frequence
    import numpy as np
    signal = audio.astype(np.float32)
    # Une réflexion très courte colore légèrement le timbre, sans longue réverbération.
    delai = max(1, int(frequence * 0.009))
    original = signal.copy()
    if len(signal) > delai:
        signal[delai:] += 0.10 * original[:-delai]
    signal /= 1.10
    # Abaissement modéré du timbre et débit un peu plus posé.
    return np.clip(signal, -32768, 32767).astype(np.int16), round(frequence * 0.94)
