"""Initialisations historiques déclenchées seulement par une entrée audio locale prête."""
from core import config
import logging
LOG = logging.getLogger("assistant.modules.legacy_tools")


def attach(app, endpoint):
    try:
        from tools.alexa import precharger_routines
        precharger_routines()
    except Exception:
        LOG.exception("Préchargement des routines")
    if config.reglage("twilio.account_sid") or config.reglage("twilio.sid"):
        try:
            from tools.appels import definir_transcripteur
            from tools.appel_direct import definir_transcripteur_direct

            definir_transcripteur(lambda source: endpoint.transcribe(source, beam_size=5))
            definir_transcripteur_direct(endpoint.transcribe)
            app.on_stop(lambda: definir_transcripteur(None))
            app.on_stop(lambda: definir_transcripteur_direct(None))
        except ImportError:
            LOG.warning("Appels configurés mais dépendances calls absentes.")
    from tools.lumieres import charger_pieces_hue, allumer_si_nuit
    for action in (charger_pieces_hue, allumer_si_nuit):
        try:
            action()
        except Exception:
            LOG.exception("Initialisation des lumières")
    for key, module, function in (
        ("presence.ip", "tools.presence", "demarrer_presence"),
        ("discord.token", "tools.discord_bot", "demarrer_discord"),
        ("instagram.comptes", "tools.instagram", "demarrer_refresh_instagram"),
    ):
        if config.reglage(key, False) or (
            key == "instagram.comptes" and config.reglage("instagram.access_token")
        ):
            try:
                from importlib import import_module

                cleanup = getattr(import_module(module), function)()
                if callable(cleanup):
                    app.on_stop(cleanup)
            except Exception:
                LOG.warning("Intégration indisponible : %s", module)


    try:
        from tools import musique
        musique.definir_capture_micro(endpoint.capture)
        app.on_stop(lambda: musique.definir_capture_micro(None))
    except Exception:
        LOG.exception("Capture musicale indisponible")
    try:
        from core import gestes
        gestes.definir_hooks(couper_tts=endpoint.stop_speech, feedback=endpoint.feedback)
        app.on_stop(gestes.arreter)
        app.on_stop(gestes.arreter_regard)
        if config.reglage("gestes.actif", False):
            LOG.info(gestes.demarrer())
        install_gesture_shortcuts(app)
    except Exception:
        LOG.exception("Initialisation des gestes")
    try:
        from tools import scenes
        scenes.jouer_au_demarrage_async()
    except Exception:
        LOG.exception("Scène au démarrage")


def install_gesture_shortcuts(app):
    """Raccourcis globaux des mains et du regard (optionnels, via keyboard)."""
    combo = config.reglage("gestes.raccourci", "ctrl+alt+g")
    combo_demo = config.reglage("gestes.raccourci_demo", "ctrl+alt+d")
    combo_regard = config.reglage("gestes.raccourci_regard", "ctrl+alt+r")
    if not combo and not combo_demo and not combo_regard:
        return
    try:
        import keyboard
    except Exception:
        return  # lib absente : le raccourci est optionnel, on continue sans
    from core import gestes

    def _toggle():
        LOG.info(gestes.arreter() if gestes.actif() else gestes.demarrer())

    def _demo():
        LOG.info(gestes.demarrer_demo())

    def _regard():
        LOG.info(
            gestes.arreter_regard()
            if gestes.regard_actif()
            else gestes.demarrer_regard()
        )

    try:
        if combo:
            app.on_stop(lambda token=keyboard.add_hotkey(combo, _toggle): keyboard.remove_hotkey(token))
            LOG.info(f"Raccourci gestes : {combo}")
        if combo_demo:
            app.on_stop(lambda token=keyboard.add_hotkey(combo_demo, _demo): keyboard.remove_hotkey(token))
            LOG.info(f"Raccourci démo gestes : {combo_demo}")
        if combo_regard:
            app.on_stop(lambda token=keyboard.add_hotkey(combo_regard, _regard): keyboard.remove_hotkey(token))
            LOG.info(f"Raccourci regard : {combo_regard}")
    except Exception:
        LOG.exception("gestes: raccourci clavier")


