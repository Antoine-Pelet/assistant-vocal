"""Attentes uniques, bornées à la session et au contexte spatial de la proposition."""

import logging
from threading import RLock
from core.contexte import current, use
from security.authorization import autoriser_toujours

LOG = logging.getLogger("assistant.confirmations")
_EN_ATTENTE = {}
_ATTENTE_LOCK = RLock()


def _cle_session():
    c = current()
    return (c.user_id, c.session_id, c.device_id, c.satellite_id)


def _attente(retirer=False):
    with _ATTENTE_LOCK:
        if not _EN_ATTENTE:
            return None
        if retirer:
            return _EN_ATTENTE.pop(_cle_session(), None)
        return _EN_ATTENTE.get(_cle_session())


def mettre_en_attente(outil_obj, args):
    with _ATTENTE_LOCK:
        return _preparer_attente(outil_obj, args)


def _preparer_attente(outil_obj, args):
    """Range une action a confirmer. Renvoie un resultat neutre pour Claude."""
    global _EN_ATTENTE
    if _attente() is not None:
        return "Une action attend déjà validation. Présente-la avant de proposer une autre modification."
    if outil_obj.nom in ("remember", "forget"):
        from tools.memoire import preparer
        from core.memoire_store import ErreurMemoire

        try:
            proposition = preparer(outil_obj.nom, args)
        except ErreurMemoire as e:
            return str(e)
        args = {
            "_memoire_proposition": proposition["jeton"],
            "_resume": proposition["resume"],
        }
    else:
        import copy

        args = copy.deepcopy(args)
    if _EN_ATTENTE is None:  # compatibilité des anciens tests et lanceurs
        _EN_ATTENTE = {}
    _EN_ATTENTE[_cle_session()] = (outil_obj, args, current())
    return "En attente de la confirmation vocale de l'utilisateur."


def annonce_en_attente():
    """Phrase a prononcer pour demander l'accord, ou None si rien en attente."""
    attente = _attente()
    if attente is None:
        return None
    outil_obj, args, contexte = attente
    if outil_obj.nom in ("remember", "forget"):
        return args["_resume"]
    if outil_obj.annonce:
        try:
            return outil_obj.annonce(args)
        except Exception:
            pass
    return f"Je vais executer {outil_obj.nom}."


def nom_en_attente():
    """Nom de l'outil en attente de confirmation (ou None)."""
    attente = _attente()
    return attente[0].nom if attente else None


def executer_confirme(memoriser=False):
    """Execute l'action en attente et renvoie son resultat.

    memoriser=True (l'utilisateur a dit "oui, toujours") : si l'outil est N2, on
    l'ajoute au 'toujours autoriser' (revocable) ; un N3 REFUSE la memorisation et
    on le lui dit, mais l'action de ce tour est quand meme executee.
    """
    attente = _attente(retirer=True)
    if attente is None:
        return ""
    outil_obj, args, contexte = attente
    with use(contexte):
        return _executer_attente(outil_obj, args, memoriser)


def _executer_attente(outil_obj, args, memoriser):
    suffixe = ""
    if memoriser:
        if autoriser_toujours(outil_obj.nom):
            suffixe = " Je ne te le redemanderai plus pour cette action."
        else:
            suffixe = " Mais c'est une action critique : je te demanderai toujours confirmation."
    try:
        if outil_obj.nom in ("remember", "forget"):
            from core import memoire
            from core.memoire_store import ErreurMemoire

            try:
                res = memoire.magasin().confirmer(
                    args["_memoire_proposition"], origine="voix"
                )
            except ErreurMemoire as e:
                return str(e)
        else:
            res = outil_obj.fonction(**args)
    except Exception:
        LOG.exception("outil confirmé « %s » a échoué", outil_obj.nom)
        return "Desole, je n'ai pas reussi a faire ca."
    return (str(res) + suffixe) if suffixe else res


def annuler_confirme():
    attente = _attente(retirer=True)
    if attente and attente[0].nom in ("remember", "forget"):
        from core import memoire

        memoire.magasin().annuler(attente[1]["_memoire_proposition"], origine="voix")
