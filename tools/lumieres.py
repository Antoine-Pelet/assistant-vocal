"""Module lumières : intentions et messages, indépendants du pilote domotique."""
from core.config import reglage
from core.registre import outil
from core.devices import DeviceError
from core.maison import devices, charger_appareils


def charger_pieces_hue():
    """Ancien nom public conservé pour les lanceurs existants."""
    charger_appareils()


def _appliquer(piece, action, parameters, resultat):
    faits = []
    try:
        catalogue = devices()
        targets = catalogue.select(piece)
        # Vérifier toutes les capacités avant de commencer une commande de groupe.
        for device in targets:
            if action not in device.capabilities:
                raise DeviceError(f"Action non disponible sur {device.name or device.id}.")
        for device in targets:
            catalogue.perform(device, action, parameters)
            faits.append(device.name or device.id)
    except DeviceError as error:
        prefixe = (", ".join(faits) + " : commande effectuée. ") if faits else ""
        return prefixe + str(error)
    return ", ".join(faits) + " : " + resultat + "."


@outil(
    nom="allumer_lumiere",
    mcp_expose=True,
    description="Allume ou eteint les lumieres d'une piece, ou de "
                "toutes les pieces. A utiliser quand l'utilisateur dit 'allume le "
                "salon', 'eteins la chambre', 'eteins tout'.",
    parametres={
        "type": "object",
        "properties": {
            "piece": {
                "type": "string",
                "description": "Nom de la piece, identifiant logique ou 'ici' "
                               "ou 'toutes' pour l'ensemble des lumieres.",
            },
            "allumer": {
                "type": "boolean",
                "description": "true pour allumer, false pour eteindre.",
            },
        },
        "required": ["piece", "allumer"],
    },
)
def allumer_lumiere(piece: str, allumer: bool = True) -> str:
    return _appliquer(piece, "turn_on" if allumer else "turn_off", {},
                       "lumiere allumee" if allumer else "lumiere eteinte")


@outil(
    nom="regler_luminosite",
    mcp_expose=True,
    description="Regle la luminosite des lumieres d'une piece en pourcentage. "
                "A utiliser pour 'baisse le salon a 30 pour cent', 'mets la chambre "
                "au maximum'.",
    parametres={
        "type": "object",
        "properties": {
            "piece": {"type": "string", "description": "Nom de la piece ou 'toutes'."},
            "pourcentage": {"type": "integer",
                            "description": "Luminosite voulue, de 0 a 100."},
        },
        "required": ["piece", "pourcentage"],
    },
)
def regler_luminosite(piece: str, pourcentage: int) -> str:
    pourcentage = max(0, min(int(pourcentage), 100))
    return _appliquer(piece, "set_brightness", {"percent": pourcentage},
                       f"{pourcentage} pour cent")


@outil(
    nom="changer_couleur",
    mcp_expose=True,
    description="Change la couleur des lumieres d'une piece a partir d'un nom "
                "de couleur en francais. Pour 'mets le salon en bleu', 'passe la "
                "chambre en rouge'.",
    parametres={
        "type": "object",
        "properties": {
            "piece": {"type": "string", "description": "Nom de la piece ou 'toutes'."},
            "couleur": {"type": "string",
                        "description": "Nom de la couleur en francais (rouge, bleu, "
                                       "vert, orange, violet, rose, blanc...)."},
        },
        "required": ["piece", "couleur"],
    },
)
def changer_couleur(piece: str, couleur: str) -> str:
    return _appliquer(piece, "set_color", {"color": couleur}, f"en {couleur}")


def allumer_si_nuit():
    """Au demarrage : allume PIECE_NUIT s'il fait deja sombre dehors.

    « Nuit » = avant le lever ou apres le coucher du soleil, calcule pour ta
    position et la date du jour (donc plus tard en ete, plus tot en hiver).
    """
    from tools.meteo import il_fait_nuit
    PIECE_NUIT = reglage("assistant.piece_nuit", "chambre")
    if not PIECE_NUIT:
        return
    try:
        devices().select(PIECE_NUIT)
    except DeviceError:
        return
    if il_fait_nuit():
        resultat = allumer_lumiere(PIECE_NUIT, True)
        print(f"  [auto] Il fait nuit -> {resultat}")
