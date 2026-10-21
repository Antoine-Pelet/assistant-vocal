"""Niveaux d'action et autorisations locales, indépendants de l'identité utilisateur."""


def _outil(nom):
    from core.tool_registry import get

    return get(nom)


_N3 = frozenset(
    {
        "envoyer_mail",
        "mettre_a_la_corbeille",
        "call_with_message",
        "call_and_book",
        "book_appointment",
        "confirmer_reservation",
        "delete_event",
        "eteindre_pc",
        "controle_pc_astra",
        "remember",
        "forget",
    }
)


def niveau(nom):
    """Niveau de permission d'un outil : N1 / N2 / N3 (ou '?' si inconnu)."""
    o = _outil(nom)
    if o is None:
        return "?"
    if nom in _N3:
        return "N3"
    declared = getattr(o, "permission_level", None)
    if declared:
        return declared
    if not o.confirmation:
        return "N1"
    return "N2"


def est_n3(nom):
    return nom in _N3 or niveau(nom) == "N3"


def autorisations():
    """Outils N2 memorises 'toujours autoriser' (config securite.toujours)."""
    from core.config import reglage

    return [n for n in (reglage("securite.toujours", []) or []) if niveau(n) == "N2"]


def est_autorise(nom):
    """Vrai si on SAUTE la confirmation EN LOCAL (N2 memorise). Jamais un N3 ni un N1."""
    return niveau(nom) == "N2" and nom in autorisations()


def autoriser_toujours(nom):
    """Memorise 'toujours autoriser' pour un N2. Renvoie True si effectif (N2 uniquement,
    jamais un N3)."""
    if niveau(nom) != "N2":
        return False
    from core.config import reglage, definir

    cur = list(reglage("securite.toujours", []) or [])
    if nom not in cur:
        cur.append(nom)
        definir("securite.toujours", cur)
    return True


def revoquer(nom):
    """Retire un outil du 'toujours autoriser'. Renvoie True si quelque chose a ete retire."""
    from core.config import reglage, definir

    cur = list(reglage("securite.toujours", []) or [])
    if nom in cur:
        cur.remove(nom)
        definir("securite.toujours", cur)
        return True
    return False
