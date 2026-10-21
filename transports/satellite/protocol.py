"""Frontière réseau du protocole PCM/JSON décrit dans docs/satellite.md."""

import ipaddress

TAUX = 16000
_MAX_UTTERANCE = TAUX * 2 * 30


def _origine_locale_ou_lan(ws) -> bool:
    """Refuse les reverse proxies et les clients hors du réseau local.

    Le tunnel ngrok termine sa connexion sur le PC en loopback, donc l'adresse
    socket seule ne suffit pas : ses en-têtes ``Forwarded``/``X-Forwarded-*``
    sont également bloqués. Un satellite réel arrive directement avec une
    adresse privée du LAN.
    """
    entetes = getattr(ws, "headers", {}) or {}
    for nom in (
        "forwarded",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
        "x-real-ip",
    ):
        if entetes.get(nom):
            return False
    client = getattr(ws, "client", None)
    hote = str(getattr(client, "host", "") or "").split("%", 1)[0]
    try:
        adresse = ipaddress.ip_address(hote)
    except ValueError:
        return False
    return adresse.is_loopback or adresse.is_private or adresse.is_link_local
