"""Satellites — Red dans une AUTRE pièce (Raspberry Pi, futur ESP32).

Un satellite est une extension du CORPS de Red (oreilles + bouche + visage
déportés). Le CERVEAU reste sur le PC : le satellite capte l'audio, le PC
transcrit (Whisper) → LLM + outils → TTS, et renvoie l'audio + des événements
d'état pour le visage/HUD du boîtier. Hermes n'est pas concerné.

PROTOCOLE (volontairement simple et transport-agnostique -> un ESP32 l'utilise
À L'IDENTIQUE) : un WebSocket /satellite, deux types de trames :
  • TRAMES TEXTE = messages de CONTRÔLE, JSON (voir docs/satellite.md) ;
  • TRAMES BINAIRES = audio PCM brut 16 bits little-endian, mono, 16 kHz.

Client -> serveur :
  {"type":"hello","satellite":"cuisine","token":"..."}   (auth + identité)
  <frames binaires PCM>                                   (pendant une phrase)
  {"type":"reveil","score":0.84}                         (arbitrage multi-micros)
  {"type":"fin_parole"}                                   (fin d'énoncé -> traiter)
  {"type":"ping"}
Serveur -> client :
  {"type":"pret","piece":"cuisine"}
  <audio court « Oui ? » si le réveil est accepté>
  {"type":"reveil_accepte|reveil_refuse","id":1,"accuse_vocal":true}
  {"type":"etat","etat":"ecoute|reflexion|parole|attente_confirmation|veille"}
  {"type":"texte","texte":"..."}                          (réponse affichable)
  {"type":"audio_debut","freq":24000}                     (puis frames binaires)
  {"type":"audio_fin"}
  {"type":"relance","secondes":8}                          (suivi sans wake word)
  {"type":"veille_forcee"}                                  (wake word requis)
  {"type":"erreur","message":"..."}

SÉCURITÉ : LAN-only (jamais exposé via ngrok — cf. la garde X-Forwarded), un
TOKEN par satellite (config satellites[].token, comparé en timing-safe). Les
actions marquées sensibles demandent la même CONFIRMATION vocale qu'au bureau :
N2 peut être mémorisé, N3 doit être reconfirmé à chaque fois.

MULTI-PIÈCES : chaque satellite a une `piece` (config) injectée en contexte -> «
allume la lumière » depuis la cuisine cible la cuisine par défaut.

MODE NUIT (prévu, PAS implémenté) : le protocole et la config laissent la place à
un satellite Pi qui, PC éteint, assurerait la domotique en autonomie et
réveillerait le PC via la Tapo (cf. wol.md). Rien ici ne le rend impossible :
le dispatch est isolé (_traiter), la détection « PC éteint » se ferait côté Pi.
"""

import asyncio
import json
import logging
import secrets
import socket
import threading
import time

from core.config import reglage
from core.contexte import ExecutionContext, use
from uuid import uuid4
from core.util import nettoyer_reponse_vocale, sans_accents

LOG = logging.getLogger("assistant.satellite")

_APP_LAN = None
_SERVEUR_LAN = None
_UVICORN_LAN = None


from transports.satellite.protocol import _origine_locale_ou_lan, TAUX, _MAX_UTTERANCE


def _satellites():
    """Dict id -> {piece, token, wake} depuis config.yaml (section satellites)."""
    out = {}
    for s in reglage("satellites", []) or []:
        if isinstance(s, dict) and s.get("id"):
            out[str(s["id"])] = {
                "piece": str(s.get("piece", "") or ""),
                "token": str(s.get("token", "") or ""),
                "wake": str(
                    s.get("wake", "appareil") or "appareil"
                ),  # "appareil" | "serveur"
                "priorite_micro": float(s.get("priorite_micro", 1.0) or 1.0),
            }
    return out


def _systeme(piece):
    from dataclasses import replace
    from core.contexte import current
    from conversation.prompt import build

    return build({}, replace(current(), room_id=piece))


from transports.satellite.session import _Session, _contexte_session

from transports.satellite.audio import _transcrire, _tts_pcm, _tts_pcm_court


def _progression_initiale(phrase):
    """Accusé contextuel uniquement si la demande annonce un travail lent.

    Les échanges simples (salutation, heure, conversation) renvoient None : ils
    ne doivent jamais être précédés d'un « attends » ou d'un « je cherche ».
    """
    p = sans_accents((phrase or "").lower())
    if any(
        m in p for m in ("mail", "mails", "email", "courriel", "boite de reception")
    ):
        return "Je regarde tes mails."
    if "recette" in p and any(
        m in p
        for m in (
            "cherche",
            "trouve",
            "propose",
            "donne-moi",
            "donne moi",
            "recommande",
        )
    ):
        return "Je cherche une recette adaptée."
    if any(
        m in p
        for m in (
            "cherche",
            "recherche",
            "sur internet",
            "sur le web",
            "trouve-moi",
            "trouve moi",
            "actualite",
            "derniere nouvelle",
            "compare",
        )
    ):
        return "Je lance la recherche."
    if any(m in p for m in ("agenda", "calendrier", "rendez-vous", "rendez vous")):
        return "Je regarde ton agenda."
    if any(
        m in p for m in ("ecran", "cette erreur", "ce message", "ce qui est affiche")
    ):
        return "Je regarde ton écran."
    if "meteo" in p or "temps fait" in p or "prevision" in p:
        return "Je regarde la météo."
    if any(m in p for m in ("facture", "recu", "recus", "depense", "budget")):
        return "Je vérifie tes informations."
    return None


def _phrase_progression(phrase):
    """Seconde étape, seulement pour une intention lente déjà reconnue."""
    p = sans_accents((phrase or "").lower())
    if any(
        m in p for m in ("mail", "mails", "email", "courriel", "boite de reception")
    ):
        return "Je parcours les messages."
    if "recette" in p and any(
        m in p
        for m in (
            "cherche",
            "trouve",
            "propose",
            "donne-moi",
            "donne moi",
            "recommande",
        )
    ):
        return "Je vérifie les propositions."
    if any(
        m in p
        for m in (
            "cherche",
            "recherche",
            "sur internet",
            "sur le web",
            "trouve-moi",
            "trouve moi",
            "actualite",
            "derniere nouvelle",
            "compare",
        )
    ):
        return "Je vérifie les résultats."
    if any(m in p for m in ("agenda", "calendrier", "rendez-vous", "rendez vous")):
        return "Je vérifie les événements."
    if "meteo" in p or "temps fait" in p:
        return "Je vérifie les prévisions."
    if any(m in p for m in ("facture", "recu", "recus", "depense", "budget")):
        return "Je termine la vérification."
    if any(
        m in p
        for m in ("allume", "eteins", "éteins", "ouvre", "ferme", "augmente", "baisse")
    ):
        return "La commande est en cours."
    return None


def _demande_veille(phrase):
    """Détecte une demande explicite de retour au mot d'activation."""
    import re
    from core.util import sans_accents

    p = " ".join(
        re.sub(r"[^a-z0-9]+", " ", sans_accents((phrase or "").lower())).split()
    )
    expressions = (
        "mets toi en veille",
        "met toi en veille",
        "active le mode veille",
        "passe en mode veille",
        "retourne en veille",
        "passe en veille",
        "va en veille",
        "dors",
        "endors toi",
        "rendors toi",
        "retourne dormir",
        "arrete d ecouter",
        "arrete de m ecouter",
        "ne m ecoute plus",
        "arrete de repondre",
        "ne reponds plus",
        "tais toi jusqu a ce que je te rappelle",
    )
    return any(expression in p for expression in expressions)


def _adresse_a_alexa(phrase):
    """Vrai lorsque la phrase est clairement destinée à l'assistant Alexa.

    Pendant la courte fenêtre de conversation suivie, le satellite écoute sans
    nouveau mot d'activation. Une commande commençant par « Alexa » appartient
    alors à l'autre assistant de la pièce : Red doit se taire et refermer sa
    fenêtre d'écoute au lieu de répondre à sa place.

    On ne filtre volontairement que le début de phrase. Une question adressée à
    Red telle que « Est-ce qu'Alexa est connectée ? » reste donc valide.
    """
    import re

    p = " ".join(
        re.sub(r"[^a-z0-9]+", " ", sans_accents((phrase or "").lower())).split()
    )
    return p == "alexa" or p.startswith("alexa ") or p.startswith("hey alexa ")


def _executer_outil(nom, args):
    """Exécute un outil après application de la politique de confirmation."""
    from core import registre

    outil = registre.get(nom)
    if outil is None:
        return f"Outil inconnu : {nom}"
    try:
        return str(outil.fonction(**(args or {})))
    except Exception:
        LOG.exception("satellite: outil %s", nom)
        return "Erreur pendant l'action."


def _executer_decision_prioritaire(session, decision):
    """DEPRECATED : le routage est exécuté par ConversationManager."""
    from conversation.manager import manager, Output

    # Compatibilité de l'ancien point d'appel, sans seconde politique de sécurité.
    from core.contexte import current

    state = manager.session(current(), session.historique)
    text = manager.execute_decision(state, decision, Output(manager, state))
    from conversation.manager import SENTINEL_CONFIRM
    from core import registre

    if text == SENTINEL_CONFIRM:
        return {
            "reponse": registre.annonce_en_attente() + " Tu confirmes ?",
            "attente_confirmation": True,
        }
    return {"reponse": text, "attente_confirmation": False}


def traiter_texte(session, phrase):
    with use(_contexte_session(session)):
        return _traiter_texte(session, phrase)


def _traiter_texte(session, phrase):
    from core.contexte import current
    from conversation.manager import manager
    from conversation.turn import ConversationTurn

    return manager.handle(ConversationTurn(phrase, current()), session.historique)


def _resoudre_confirmation(session, phrase):
    with use(_contexte_session(session)):
        return _resoudre_confirmation_contextuelle(session, phrase)


def _resoudre_confirmation_contextuelle(session, phrase):
    from core import registre
    from core.memoire_store import accord_explicite

    if not accord_explicite(phrase):
        registre.annuler_confirme()
        return "D'accord, j'annule."
    return registre.executer_confirme(memoriser="toujours" in phrase.lower())


# ---------------------------------------------------------------- WebSocket


def monter_routes(app):
    """Monte le WebSocket /satellite sur le serveur unifié (appelé par core.serveur)."""
    from fastapi import WebSocket, WebSocketDisconnect

    @app.websocket("/satellite")
    async def satellite(ws: WebSocket):
        if not _origine_locale_ou_lan(ws):
            LOG.warning("satellite: connexion hors LAN refusee")
            await ws.close(
                code=1008, reason="satellite accessible uniquement sur le LAN"
            )
            return
        await ws.accept()
        cfg = _satellites()
        sess = _Session()

        async def envoyer(obj):
            await ws.send_text(json.dumps(obj, ensure_ascii=False))

        async def etat(e):
            await envoyer({"type": "etat", "etat": e})

        async def envoyer_audio(texte, court=False):
            synthese = _tts_pcm_court if court else _tts_pcm
            pcm, freq = await asyncio.to_thread(
                synthese, texte, _contexte_session(sess)
            )
            if pcm:
                await envoyer({"type": "audio_debut", "freq": freq})
                for i in range(0, len(pcm), 4096):
                    await ws.send_bytes(pcm[i : i + 4096])
                await envoyer({"type": "audio_fin"})
                return True
            return False

        async def parler(texte):
            """Envoie le texte (affichage) puis l'audio TTS (frames binaires)."""
            await envoyer({"type": "texte", "texte": texte})
            await etat("parole")
            await envoyer_audio(texte)

        async def progresser(texte):
            """Parle brièvement sans ajouter l'accusé à l'historique LLM."""
            await envoyer({"type": "progression", "texte": texte})
            await etat("parole")
            await envoyer_audio(texte, court=True)
            await etat("reflexion")

        async def proposer_relance(secondes=None, obligatoire=False):
            if not bool(reglage("satellite_lan.conversation_suivie", True)):
                return
            if not sess.autoriser_relance(obligatoire=obligatoire):
                # Ferme aussi une éventuelle fenêtre devenue obsolète côté
                # client. Un bruit de cuisine ne peut ainsi pas renouveler
                # indéfiniment l'écoute sans nouveau « Hey Red ».
                await envoyer({"type": "veille_forcee"})
                return
            try:
                duree = float(
                    secondes
                    if secondes is not None
                    else reglage("satellite_lan.fenetre_relance", 8.0)
                )
            except (TypeError, ValueError):
                duree = 8.0
            duree = max(0.0, min(duree, 30.0))
            if duree:
                await envoyer({"type": "relance", "secondes": duree})

        try:
            while True:
                msg = await ws.receive()
                # 1) trame binaire = audio PCM
                if "bytes" in msg and msg["bytes"] is not None:
                    if sess.satellite is None:  # pas encore authentifié
                        continue
                    sess.audio.extend(msg["bytes"])
                    if len(sess.audio) > _MAX_UTTERANCE:
                        sess.audio = sess.audio[-_MAX_UTTERANCE:]
                    continue
                # 2) trame texte = contrôle
                if "text" not in msg or msg["text"] is None:
                    if msg.get("type") == "websocket.disconnect":
                        break
                    continue
                try:
                    data = json.loads(msg["text"])
                except Exception:
                    continue
                typ = data.get("type")

                if typ == "hello":
                    sid = str(data.get("satellite", ""))
                    conf = cfg.get(sid)
                    if (
                        not conf
                        or not conf["token"]
                        or not secrets.compare_digest(
                            str(data.get("token", "")), conf["token"]
                        )
                    ):
                        await envoyer(
                            {
                                "type": "erreur",
                                "message": "satellite inconnu ou token invalide",
                            }
                        )
                        await ws.close(code=1008)
                        return
                    sess.satellite, sess.piece = sid, conf["piece"]
                    LOG.info(
                        "satellite connecté : %s (pièce %s)", sid, sess.piece or "?"
                    )
                    await envoyer({"type": "pret", "piece": sess.piece})
                    await etat("veille")

                elif typ == "reveil" and sess.satellite:
                    from core.arbitrage_micro import reserver_reveil

                    try:
                        score = float(data.get("score", 0.0))
                    except (TypeError, ValueError):
                        score = 0.0
                    priorite = cfg[sess.satellite].get("priorite_micro", 1.0)
                    accepte = await asyncio.to_thread(
                        reserver_reveil,
                        f"satellite:{sess.satellite}",
                        score * priorite,
                    )
                    if accepte:
                        sess.nouveau_reveil(reglage("satellite_lan.max_relances", 2))
                    accuse_vocal = False
                    if accepte and bool(
                        reglage("satellite_lan.accuse_reveil_vocal", True)
                    ):
                        texte_accuse = str(
                            reglage("satellite_lan.texte_accuse_reveil", "Oui ?") or ""
                        ).strip()
                        try:
                            delai_accuse = float(
                                reglage("satellite_lan.delai_accuse_reveil", 2.5)
                            )
                        except (TypeError, ValueError):
                            delai_accuse = 2.5
                        if texte_accuse:
                            try:
                                # L'audio part AVANT l'autorisation de capture :
                                # le Pi le joue pendant que son thread micro attend,
                                # puis commence seulement à enregistrer la question.
                                accuse_vocal = await asyncio.wait_for(
                                    envoyer_audio(texte_accuse, court=True),
                                    timeout=max(0.5, min(delai_accuse, 5.0)),
                                )
                            except asyncio.TimeoutError:
                                LOG.warning(
                                    "satellite: accusé vocal trop lent, repli sur le bip"
                                )
                    await envoyer(
                        {
                            "type": "reveil_accepte" if accepte else "reveil_refuse",
                            "id": data.get("id"),
                            "accuse_vocal": accuse_vocal,
                        }
                    )

                elif typ == "fin_parole" and sess.satellite:
                    audio = bytes(sess.audio)
                    sess.audio = bytearray()
                    await etat("reflexion")
                    # On ne connaît pas encore l'intention pendant Whisper : toute
                    # phrase d'attente ici serait nécessairement générique et peut
                    # parasiter une simple salutation. La progression ne commence
                    # qu'après transcription, lorsque la demande le justifie.
                    phrase = await asyncio.to_thread(
                        _transcrire, audio, _contexte_session(sess)
                    )
                    if not phrase:
                        await parler("Je n'ai rien entendu.")
                        await proposer_relance()
                        await etat("veille")
                        continue
                    await envoyer({"type": "transcription", "texte": phrase})
                    if _adresse_a_alexa(phrase):
                        # Ne jamais lutter avec un Echo présent dans la pièce.
                        # Le silence est intentionnel : la demande ne visait pas
                        # Red et ne doit pas rouvrir la conversation suivie.
                        sess.en_attente = None
                        sess.mettre_en_veille()
                        await envoyer({"type": "veille_forcee"})
                        await etat("veille")
                        continue
                    if _demande_veille(phrase):
                        # Une mise en veille annule aussi une éventuelle action N3
                        # encore en attente : elle ne doit jamais être confirmée plus tard.
                        sess.en_attente = None
                        sess.mettre_en_veille()
                        await parler("D'accord, je me mets en veille.")
                        await envoyer({"type": "veille_forcee"})
                        await etat("veille")
                        continue
                    if sess.en_attente:  # réponse à une confirmation N3
                        rep = _resoudre_confirmation(sess, phrase)
                        await parler(rep)
                        await proposer_relance()
                        await etat("veille")
                        continue
                    traitement = asyncio.create_task(
                        asyncio.to_thread(traiter_texte, sess, phrase)
                    )
                    progression_initiale = None
                    if bool(reglage("satellite_lan.accuse_immediat", True)):
                        progression_initiale = _progression_initiale(phrase)
                    if progression_initiale:
                        await progresser(progression_initiale)
                    try:
                        attente_llm = float(
                            reglage("satellite_lan.progression_traitement_apres", 4.0)
                        )
                    except (TypeError, ValueError):
                        attente_llm = 4.0
                    try:
                        r = await asyncio.wait_for(
                            asyncio.shield(traitement), timeout=max(0.1, attente_llm)
                        )
                    except asyncio.TimeoutError:
                        suite = _phrase_progression(phrase)
                        if suite:
                            await progresser(suite)
                        r = await traitement
                    if r["attente_confirmation"]:
                        await envoyer({"type": "texte", "texte": r["reponse"]})
                        await etat("attente_confirmation")
                        await envoyer_audio(r["reponse"])
                        await proposer_relance(12.0, obligatoire=True)
                    else:
                        await parler(r["reponse"])
                        await proposer_relance()
                        await etat("veille")

                elif typ == "ping":
                    await envoyer({"type": "pong"})

        except WebSocketDisconnect:
            pass
        except Exception:
            LOG.exception("satellite: boucle WS")
        finally:
            from conversation.manager import manager

            manager.close(_contexte_session(sess))
            LOG.info("satellite déconnecté : %s", sess.satellite)

    LOG.info("satellite: route /satellite montée (LAN, token par satellite)")


def _app_lan():
    """Application FastAPI minimale exposée au LAN : `/satellite` seulement."""
    global _APP_LAN
    if _APP_LAN is None:
        from fastapi import FastAPI

        _APP_LAN = FastAPI(
            title="Red Satellite LAN",
            docs_url=None,
            redoc_url=None,
            openapi_url=None,
        )
        monter_routes(_APP_LAN)
    return _APP_LAN


def demarrer_lan():
    """Démarre le listener satellite dédié sans exposer le serveur unifié.

    Le port n'est ouvert que lorsqu'au moins un satellite est configuré. Le
    panneau, le cockpit, l'inbox iPhone et Twilio restent sur le listener
    loopback principal.
    """
    global _SERVEUR_LAN, _UVICORN_LAN
    if not _satellites() or not bool(reglage("satellite_lan.actif", True)):
        return
    if _SERVEUR_LAN and _SERVEUR_LAN.is_alive():
        return

    import uvicorn

    hote = str(reglage("satellite_lan.host", "0.0.0.0") or "0.0.0.0")
    port = int(reglage("satellite_lan.port", 8791))
    serveur = uvicorn.Server(
        uvicorn.Config(_app_lan(), host=hote, port=port, log_level="warning")
    )
    _UVICORN_LAN = serveur

    def run():
        try:
            serveur.run()
        except Exception:
            LOG.exception("satellite: serveur LAN")

    _SERVEUR_LAN = threading.Thread(target=run, daemon=True, name="satellite-lan")
    _SERVEUR_LAN.start()

    # Prépare le très court « Oui ? » dès le démarrage. Le premier wake word ne
    # paie ainsi normalement ni la latence réseau ni la synthèse cloud.
    if bool(reglage("satellite_lan.accuse_reveil_vocal", True)):
        texte_accuse = str(
            reglage("satellite_lan.texte_accuse_reveil", "Oui ?") or ""
        ).strip()
        if texte_accuse:
            threading.Thread(
                target=_tts_pcm_court,
                args=(texte_accuse,),
                daemon=True,
                name="satellite-accuse-reveil",
            ).start()
    for _ in range(40):
        try:
            socket.create_connection(("127.0.0.1", port), 0.15).close()
            break
        except OSError:
            time.sleep(0.15)
    LOG.info("satellite: listener LAN actif sur %s:%d", hote, port)


def arreter_lan():
    global _SERVEUR_LAN, _UVICORN_LAN, _APP_LAN
    if _UVICORN_LAN:
        _UVICORN_LAN.should_exit = True
    if _SERVEUR_LAN and _SERVEUR_LAN is not threading.current_thread():
        _SERVEUR_LAN.join(timeout=5)
    _SERVEUR_LAN = None
    _UVICORN_LAN = None
    _APP_LAN = None
