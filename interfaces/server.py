"""Serveur web unifie de Red : UN seul FastAPI / UN seul port pour tout.

Regroupe, sous un unique tunnel ngrok :
  - le pont iPhone      -> POST /api/inbox        (core.pont_iphone)
  - le webhook Twilio   -> WebSocket /stream      (tools.appel_direct, appels V2)
  - les futures PWA     -> a monter ici (routes /...)

Ainsi ton domaine ngrok statique sert TOUT. Config : section `serveur`
(actif/port/public_url/ngrok_authtoken). Les anciennes cles (pont_iphone.port,
twilio.public_url/ngrok_authtoken, appels.port_stream) restent lues en repli.
"""

import logging
import socket
import threading

# Magasin de certificats Windows : indispensable AVANT pyngrok, dont l'installeur
# telecharge le binaire ngrok en TLS (Malwarebytes intercepte -> sinon "certificate
# verify failed" et le tunnel ne s'ouvre jamais).
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

from core.config import reglage

LOG = logging.getLogger("assistant")

_APP = None
_SERVEUR = None
_UVICORN = None
_URL = None


def _port():
    return int(
        reglage(
            "serveur.port",
            reglage("pont_iphone.port", reglage("appels.port_stream", 8790)),
        )
    )


def app():
    """Serveur unique ; aucune interface ni connexion optionnelle montée implicitement."""
    global _APP
    if _APP is None:
        from fastapi import FastAPI

        _APP = FastAPI(title="Red", docs_url=None, redoc_url=None, openapi_url=None)
        if reglage("admin.enabled", True):
            from interfaces.admin.controller import monter_routes

            monter_routes(_APP)
        if reglage("pont_iphone.actif", False):
            from transports.iphone.server import monter_routes

            monter_routes(_APP)
        if reglage("gestes.actif", False):
            from core.gestes import monter_routes

            monter_routes(_APP)
        if reglage("twilio.sid", "") or reglage("twilio.account_sid", ""):
            from tools.appel_direct import monter_ws

            monter_ws(_APP)
        if reglage("satellites", []):
            from transports.satellite.server import monter_routes

            monter_routes(_APP)
    return _APP


def _port_ouvert(port, timeout=0.3):
    try:
        socket.create_connection(("127.0.0.1", port), timeout).close()
        return True
    except OSError:
        return False


def demarrer():
    """Lance le serveur unifie en tache de fond (idempotent). Attend qu'il ecoute."""
    global _SERVEUR, _UVICORN
    port = _port()
    if _SERVEUR and _SERVEUR.is_alive():
        return
    import time
    import uvicorn
    from core import memoire

    memoire.magasin()  # Purge au lancement, puis à chaque échéance des sept jours.
    # SÉCURITÉ : loopback par défaut. Le tunnel ngrok se connecte en 127.0.0.1
    # (aucun impact) ; le panneau/cockpit/gestes ne sont donc PAS exposés au LAN.
    # Ne passe à "0.0.0.0" que si tu SAIS ce que tu fais (accès réseau local).
    hote = reglage("serveur.host", "127.0.0.1")
    config = uvicorn.Config(app(), host=hote, port=port, log_level="warning")
    serveur = uvicorn.Server(config)
    _UVICORN = serveur

    def run():
        try:
            serveur.run()  # uvicorn n'installe pas les handlers de signaux hors main thread
        except Exception:
            LOG.exception("serveur web")

    _SERVEUR = threading.Thread(target=run, daemon=True, name="serveur-web")
    _SERVEUR.start()
    for _ in range(40):  # attend l'ouverture du port (max ~6 s)
        if _port_ouvert(port):
            break
        time.sleep(0.15)
    # Listener LAN séparé : il ne contient QUE /satellite. Le serveur unifié
    # reste en loopback, donc panneau/cockpit/inbox/Twilio ne gagnent aucun accès
    # réseau lorsqu'un Raspberry Pi est configuré.
    try:
        from core.satellite import demarrer_lan

        demarrer_lan()
    except Exception:
        LOG.exception("demarrage du listener satellite LAN")
    # Ouvre le tunnel ngrok automatiquement (si authtoken configure et pas d'URL
    # manuelle) pour que l'endpoint soit joignable des le demarrage.
    try:
        _ouvrir_tunnel()
    except Exception:
        LOG.exception("ouverture du tunnel ngrok")
    print(f"Serveur web : port {port} (iPhone /api/inbox, Twilio /stream).")


def _ouvrir_tunnel():
    """Ouvre le tunnel ngrok en mode AUTO : authtoken configure, pas d'URL manuelle.
    Utilise ton domaine STATIQUE si serveur.ngrok_domaine est renseigne.
    Degrade proprement (message clair) si l'antivirus bloque ngrok."""
    global _URL
    if reglage("serveur.public_url", "") or reglage("twilio.public_url", ""):
        return  # tu geres ton tunnel toi-meme (CLI)
    if _URL:
        return
    tok = reglage("serveur.ngrok_authtoken", "") or reglage(
        "twilio.ngrok_authtoken", ""
    )
    if not tok:
        return
    from pyngrok import ngrok

    try:
        ngrok.set_auth_token(tok)
        domaine = reglage("serveur.ngrok_domaine", "")
        options = {"domain": domaine} if domaine else {}
        _URL = ngrok.connect(_port(), "http", **options).public_url
        LOG.info("tunnel ngrok ouvert : %s", _URL)
        print(f"Tunnel ngrok ouvert : {_URL}")
    except Exception as e:
        _URL = None
        msg = str(e)
        if "certificate" in msg or "x509" in msg or "unknown authority" in msg:
            # Cas connu : un antivirus (Avast Web Shield) intercepte et BLOQUE ngrok
            # avec un certificat "Untrusted Root" -> l'agent ne peut pas s'authentifier.
            LOG.error(
                "tunnel ngrok bloque par l'antivirus (certificat non fiable). "
                "Ajoute une exception Avast pour connect.ngrok-agent.com et *.ngrok-free.app, "
                "ou utilise un tunnel lance a la main (serveur.public_url). Voir docs/iphone.md."
            )
            print(
                "ATTENTION : le tunnel ngrok est bloque par l'antivirus (Avast). "
                "Le serveur local tourne mais n'est pas joignable de l'exterieur. "
                "Ajoute une exception Avast (voir docs/iphone.md) puis relance."
            )
        else:
            LOG.exception("ouverture du tunnel ngrok")
            print(f"Tunnel ngrok indisponible : {msg[:120]}")


def url_publique():
    """Base publique https:// : URL manuelle, sinon le tunnel ngrok auto."""
    manuel = reglage("serveur.public_url", "") or reglage("twilio.public_url", "")
    if manuel:
        return manuel.rstrip("/")
    if not _URL:
        _ouvrir_tunnel()
    return _URL or ""


def url_ws():
    """Base wss:// (pour l'URL du <Stream> de Twilio)."""
    return url_publique().replace("https://", "wss://").replace("http://", "ws://")


def arreter():
    global _SERVEUR, _UVICORN, _APP, _URL
    if _UVICORN:
        _UVICORN.should_exit = True
    if _SERVEUR and _SERVEUR is not threading.current_thread():
        _SERVEUR.join(timeout=5)
    from transports.satellite.server import arreter_lan

    arreter_lan()
    if _URL:
        try:
            from pyngrok import ngrok

            ngrok.disconnect(_URL)
        except Exception:
            LOG.warning("Tunnel déjà fermé ou indisponible.")
    _SERVEUR = None
    _UVICORN = None
    _APP = None
    _URL = None
