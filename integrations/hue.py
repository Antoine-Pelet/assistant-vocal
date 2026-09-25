"""Pilote Philips Hue local ; aucun outil métier n'importe ce protocole."""
from core.devices import Device, DeviceError
import difflib
import json
import urllib.request

from core.config import reglage
from core.util import sans_accents


# Pieces connues du pont, remplies au demarrage : {nom_normalise: (id, nom)}.
_PIECES_HUE = {}

# Couleurs par nom francais -> (teinte, saturation) au format Hue.
# La teinte va de 0 a 65535, la saturation de 0 (blanc) a 254 (couleur vive).
_COULEURS_HUE = {
    "rouge": (0, 254),
    "orange": (5000, 254),
    "jaune": (10000, 254),
    "vert": (25500, 254),
    "turquoise": (32000, 254),
    "cyan": (35000, 254),
    "bleu": (46920, 254),
    "indigo": (48000, 254),
    "violet": (50000, 254),
    "magenta": (54000, 254),
    "rose": (56100, 254),
    "blanc": (0, 0),
}


def _hue_requete(chemin, methode="GET", corps=None):
    """Appelle l'API locale du pont Hue. Renvoie le JSON decode ou leve."""
    pont, cle = reglage("hue.pont", ""), reglage("hue.cle", "")
    url = f"http://{pont}/api/{cle}/{chemin}"
    donnees = json.dumps(corps).encode("utf-8") if corps is not None else None
    requete = urllib.request.Request(url, data=donnees, method=methode)
    if donnees is not None:
        requete.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(requete, timeout=5) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


def charger_pieces_hue():
    """Recupere les pieces (groups) du pont pour pouvoir les nommer a la voix."""
    _PIECES_HUE.clear()
    try:
        groupes = _hue_requete("groups")
    except Exception:
        print("Philips Hue indisponible.")
        return
    for ident, groupe in groupes.items():
        nom = groupe.get("name", "")
        if nom:
            _PIECES_HUE[sans_accents(nom)] = (ident, nom)
    if _PIECES_HUE:
        noms = ", ".join(v[1] for v in _PIECES_HUE.values())
        print(f"Philips Hue : {len(_PIECES_HUE)} piece(s) : {noms}")


def _cible_hue(piece):
    """Renvoie (id, nom_lisible) pour une piece ou pour toutes les lumieres.

    Le groupe 0 designe l'ensemble des lumieres cote pont. La comparaison est
    souple : Whisper transcrit mal et l'utilisateur dit "le salon", pas "salon".
    Renvoie None si la piece reste introuvable.
    """
    cible = sans_accents(piece.strip())
    if cible in ("toutes", "tout", "toute", "partout", "toutes les pieces",
                 "toutes les lumieres", "la maison", "maison"):
        return ("0", "Toutes les lumieres")

    if cible in _PIECES_HUE:
        return _PIECES_HUE[cible]

    meilleur, score_max = None, 0.0
    for norme, (ident, nom) in _PIECES_HUE.items():
        if norme in cible or cible in norme:
            return (ident, nom)
        score = difflib.SequenceMatcher(None, cible, norme).ratio()
        if score > score_max:
            meilleur, score_max = (ident, nom), score
    return meilleur if score_max >= 0.6 else None


def _agir_hue(ident, action):
    """Applique une action sur un groupe. Renvoie True si le pont a accepte."""
    reponses = _hue_requete(f"groups/{ident}/action", "PUT", action)
    return bool(reponses) and all("success" in r for r in reponses)



class HueIntegration:
    def resolve_legacy(self, target, kind):
        if kind != "light":
            return None
        found = _cible_hue(target)
        if found is None:
            return None
        ident, name = found
        return Device("hue.group." + ident, "light", "hue", ident,
                      frozenset({"turn_on", "turn_off", "set_brightness", "set_color"}), name)

    def execute(self, device, action, parameters, context):
        if action in {"turn_on", "turn_off"}:
            body = {"on": action == "turn_on"}
        elif action == "set_brightness":
            percent = max(0, min(int(parameters["percent"]), 100))
            body = ({"on": True, "bri": max(1, round(percent / 100 * 254))}
                    if percent else {"on": False})
        elif action == "set_color":
            color = sans_accents(parameters["color"].strip())
            value = _COULEURS_HUE.get(color)
            if value is None and color:
                value = next((v for name, v in _COULEURS_HUE.items()
                              if name in color or color in name), None)
            if value is None:
                raise DeviceError("Couleur inconnue.")
            body = {"on": True, "hue": value[0], "sat": value[1]}
        else:
            raise DeviceError("Action non prise en charge par cette lumière.")
        return _agir_hue(device.address, body)
