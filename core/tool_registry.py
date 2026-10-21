"""Registre d'outils : decorateur @outil, auto-decouverte, confirmation vocale.

Chaque outil est une fonction decoree par @outil dans un fichier de tools/.
Au demarrage, charger_outils() importe tous les modules de tools/ pour peupler
le registre. Le reste de l'assistant n'a plus a connaitre les outils un par un.
"""

import importlib
import logging
import pkgutil
from threading import RLock
from core.contexte import current, use

LOG = logging.getLogger("assistant.registre")

_REGISTRE = {}  # nom -> Outil


class Outil:
    """Metadonnees + fonction d'un outil."""

    def __init__(
        self,
        fonction,
        nom,
        description,
        parametres,
        confirmation,
        lent,
        phrase_attente,
        annonce,
        mcp_expose,
        affichage="auto",
        permission_level=None,
    ):
        self.fonction = fonction
        self.nom = nom
        self.description = description
        self.parametres = parametres
        self.confirmation = confirmation  # demande "tu confirmes ?" avant d'agir
        self.permission_level = permission_level
        self.lent = lent  # accuse de reception pendant l'execution
        self.phrase_attente = phrase_attente  # phrase d'attente si lent
        self.annonce = annonce  # fn(args) -> phrase de confirmation
        self.mcp_expose = mcp_expose  # visible via le serveur MCP externe ?
        self.affichage = affichage  # overlay : "toujours" | "jamais" | "auto"
        # Domaine déduit du module (tools.mail -> mail). Il permet de ne transmettre
        # au LLM que les outils utiles à la demande courante.
        self.module = fonction.__module__.rsplit(".", 1)[-1]


def outil(
    nom,
    description,
    parametres=None,
    confirmation=False,
    lent=False,
    phrase_attente=None,
    annonce=None,
    mcp_expose=False,
    affichage="auto",
    permission_level=None,
):
    """Decorateur : enregistre une fonction comme outil de l'assistant.

    mcp_expose : par securite, un outil n'est PAS expose au serveur MCP par
    defaut (un agent externe ne doit voir que ce qu'on autorise explicitement).
    affichage : routage de l'overlay de reponses. "toujours" (musique, stats,
    listes, minuteurs, retours Hermes), "jamais" (acquittement ephemere), ou
    "auto" (defaut : heuristique cote core selon le contenu de la reponse).
    """

    if permission_level not in {None, "N1", "N2", "N3"}:
        raise ValueError("Niveau de permission invalide.")
    if permission_level == "N1" and confirmation:
        raise ValueError("N1 ne peut pas supprimer une confirmation explicite.")
    confirmation = confirmation or permission_level in {"N2", "N3"}

    def deco(fonction):
        _REGISTRE[nom] = Outil(
            fonction,
            nom,
            description,
            parametres or {"type": "object", "properties": {}},
            confirmation,
            lent,
            phrase_attente,
            annonce,
            mcp_expose,
            affichage,
            permission_level,
        )
        return fonction

    return deco


def affichage(nom):
    """Hint d'affichage overlay d'un outil : 'toujours' | 'jamais' | 'auto'."""
    o = _REGISTRE.get(nom)
    return getattr(o, "affichage", "auto") if o else "auto"


def charger_outils():
    """Importe tous les modules de tools/ pour remplir le registre.

    Chaque module est isolé : si l'un rate son import (dépendance optionnelle
    absente sur la machine de l'utilisateur), on le loggue et on CONTINUE — les
    autres outils se chargent quand même. Sans ça, un seul import cassé faisait
    disparaître silencieusement tous les outils suivants."""
    import tools

    echecs = []
    for module in pkgutil.iter_modules(tools.__path__):
        if module.name == "reponses":
            continue  # overlay déprécié
        try:
            importlib.import_module(f"tools.{module.name}")
        except Exception as e:
            echecs.append(module.name)
            LOG.warning(
                "outil « %s » non chargé (dépendance manquante ?) : %s",
                module.name,
                e,
                exc_info=True,
            )
    if echecs:
        LOG.warning("%d outil(s) ignoré(s) : %s", len(echecs), ", ".join(echecs))


def get(nom):
    return _REGISTRE.get(nom)


def retirer(nom, attendu):
    """Retire uniquement l'outil possédé par l'extension qui s'arrête."""
    if _REGISTRE.get(nom) is attendu:
        del _REGISTRE[nom]


def tous():
    return list(_REGISTRE.values())


# Outils NON exposes au modele local : soit ils exigent de la vision/un raisonnement
# agentique cloud, soit ils noieraient un petit modele. `browser_open` reste permis :
# ouvrir explicitement une URL ne demande aucune vision ni intelligence cloud.
_NON_LOCAUX = {
    "capture_screen",
    "faire_brief",
    "lire_mails",
    "lire_mail",
    "preparer_mail",
    "envoyer_mail",
    "mettre_a_la_corbeille",
    "get_events",
    "create_event",
    "delete_event",
    "get_deadlines",
    "chercher_web",
    "book_appointment",
    "confirmer_reservation",
    "browser_current_page",
    "browser_tabs",
    "browser_close_tabs",
    "browser_interact",
    "lire_netflix",
    "controle_pc_astra",
    "call_with_message",
    "call_and_book",
    "cout_appels",
    "instagram_resume",
    "rafraichir_instagram",
    "get_mentions_summary",
    "get_channel_summary",
}


def schemas_api(local_seulement=False, modules=None):
    """Schemas au format Anthropic (name, description, input_schema).

    local_seulement=True : ne renvoie que les outils utilisables par un modele
    local (mode Ollama), en excluant les outils internet/vision (_NON_LOCAUX).
    modules : ensemble optionnel de domaines (noms de fichiers dans tools/).
    None conserve tout le catalogue ; un ensemble vide n'expose aucun outil.
    """
    return [
        {"name": o.nom, "description": o.description, "input_schema": o.parametres}
        for o in _REGISTRE.values()
        if not (local_seulement and o.nom in _NON_LOCAUX)
        and (modules is None or o.module in modules or getattr(o, "extension", None))
    ]


def noms_lents():
    return {o.nom for o in _REGISTRE.values() if o.lent}


def exposes_mcp():
    """Liste des outils autorises a etre exposes via le serveur MCP externe."""
    return [o for o in _REGISTRE.values() if o.mcp_expose]


# ---------------------------------------------------- niveaux de permission (N8)
#
# N1 (sur)      : pas de confirmation -> execute direct, EN LOCAL ET a distance.
# N2 (sensible) : confirmation ; l'utilisateur peut memoriser "toujours autoriser"
#                 (revocable) -> plus de question EN LOCAL ; jamais en auto a distance.
# N3 (critique) : confirmation TOUJOURS ; "toujours" REFUSE ; jamais a distance.
#                 Verrouille ici. (Le pont iPhone refuse deja tout outil a confirmation,
#                 quel que soit le store : le "toujours autoriser" n'ouvre RIEN a distance.)


def phrase_attente(noms):
    """Phrase d'accuse de reception pour le premier outil lent appele."""
    for o in _REGISTRE.values():
        if o.nom in noms and o.lent and o.phrase_attente:
            return o.phrase_attente
    return "D'accord, je m'en occupe."


# ---------------------------------------------------------------- confirmation


# Compatibilité API des outils : implémentations uniques dans security/.
from security.authorization import (
    niveau,
    est_n3,
    autorisations,
    est_autorise,
    autoriser_toujours,
    revoquer,
    _N3,
)
from security.confirmations import (
    mettre_en_attente,
    annonce_en_attente,
    nom_en_attente,
    executer_confirme,
    annuler_confirme,
)
