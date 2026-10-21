"""Catalogue de voix locales. Les identifiants publics ne sont pas des chemins."""

from pathlib import Path

from core.config import reglage

RACINE = Path(__file__).resolve().parents[2]
PROFILS = {
    "tom_fr": {
        "nom": "Tom — français",
        "description": "Voix locale légère de secours.",
        "modele": "voix/fr_FR-tom-medium.onnx",
        "effet": None,
    },
}


def selection():
    return "tom_fr"


def installee(identifiant):
    profil = PROFILS.get(identifiant)
    if not profil:
        return False
    chemin = RACINE / profil["modele"]
    return chemin.is_file() and chemin.with_suffix(".onnx.json").is_file()


def catalogue():
    active = selection()
    return [
        {
            "id": identifiant,
            "nom": p["nom"],
            "description": p["description"],
            "installee": installee(identifiant),
            "active": identifiant == active,
        }
        for identifiant, p in PROFILS.items()
    ]


def appliquer_effet(audio, frequence, identifiant):
    """Compatibilité de l'API ; pas d'effet personnage sur le secours Piper."""
    return audio, frequence
