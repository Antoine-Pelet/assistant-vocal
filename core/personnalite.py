"""Personnalites de l'assistant : presets qui modifient la consigne systeme."""
from core.util import sans_accents

# Chaque preset est une phrase de caractere prependee a la consigne systeme.
PRESETS = {
    "jarvis_sarcastique": (
        "Tu es Red. Réponds brièvement, sur un ton calme et extrêmement poli. "
        "Privilégie les formulations précises, élégantes et concises, légèrement "
        "britanniques. Utilise parfois « Monsieur ». Ton humour est sec et subtil ; "
        "une légère ironie est permise lorsqu'elle est appropriée, jamais agressive "
        "ni familière. Reste imperturbable même face à l'absurde. "
        "N'ajoute jamais d'exclamations inutiles. Reste efficace et utile."
    ),
    "neutre": (
        "Tu es un assistant neutre, factuel et serviable, sans fioritures."
    ),
    "concis": (
        "Tu es extremement concis : tu vas droit au but, idealement en une phrase, "
        "sans formule de politesse superflue."
    ),
}

DEFAUT = "neutre"


def persona(nom):
    """Renvoie le texte de personnalite pour un preset (defaut si inconnu)."""
    return PRESETS.get(nom, PRESETS[DEFAUT])


def normaliser(mode):
    """Ramene une formulation libre a un nom de preset connu."""
    m = sans_accents(mode).strip()
    if m in {"red", "mode red", "red sarcastique"} or "jarvis" in m or "sarcas" in m or "iron" in m or "stark" in m:
        return "jarvis_sarcastique"
    if "concis" in m or "court" in m or "bref" in m or "rapide" in m:
        return "concis"
    if "neutre" in m or "normal" in m or "standard" in m or "classique" in m:
        return "neutre"
    return m
