import re
from core.util import sans_accents

_REFERENCES_ECRAN = (
    "ecran", "affiche", "cette erreur", "ce message", "cette fenetre",
    "cette page", "ce texte", "ce qui est ouvert", "ce que tu vois",
)
_INTENTIONS_VISION = (
    "lis", "lire", "regarde", "voir", "decris", "decrire", "explique",
    "expliquer", "traduis", "traduire", "c est quoi", "qu est ce que",
    "que vois tu", "qu est ce qui",
)
_ACTIONS_ECRAN = (
    "clique", "double clique", "tape ", "saisis", "ouvre", "ferme", "deplace",
    "active", "desactive", "selectionne", "configure", "installe", "supprime",
)


def est_demande_vision_ecran(phrase: str) -> bool:
    """Vrai pour une lecture visuelle sans action sur l'interface."""
    p = " ".join(re.sub(
        r"[^a-z0-9]+", " ", sans_accents(str(phrase or "").lower())
    ).split())
    if any(action in p for action in _ACTIONS_ECRAN):
        return False
    return (any(ref in p for ref in _REFERENCES_ECRAN)
            and any(intent in p for intent in _INTENTIONS_VISION))


