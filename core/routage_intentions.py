"""Façade compatible du routage ; les décisions appartiennent aux modules."""
from dataclasses import replace
from core.contexte import current


def decider_prioritaire(phrase, piece=""):
    from assistant_vocal.runtime import runtime
    runtime.start()
    return runtime.capabilities.route(phrase, replace(current(), room_id=piece or current().room_id))


def modules_pour_phrase(phrase):
    from assistant_vocal.runtime import runtime
    runtime.start()
    return runtime.capabilities.select_domains(phrase)


def est_demande_vision_ecran(phrase):
    # Import historique : les nouveaux consommateurs utilisent les capabilities.
    from modules.vision.intents import est_demande_vision_ecran as detect
    return detect(phrase)
