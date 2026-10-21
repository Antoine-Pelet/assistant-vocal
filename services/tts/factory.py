"""Chatterbox principal, Piper puis Windows comme replis locaux."""

import logging
from threading import RLock

_LOCK = RLock()
from core.config import reglage
from services.tts.piper import PiperProvider
from services.tts.windows import WindowsProvider
from services.tts.elevenlabs import ElevenLabsProvider

LOG = logging.getLogger("assistant.tts")
_TTS = None


def tts():
    with _LOCK:
        """Provider TTS courant.

        ``tts.engine`` peut valoir chatterbox/piper/windows/elevenlabs. Le mode
        local garde sa promesse de confidentialite : ElevenLabs y est ignore et un
        moteur local est choisi.
        """
        global _TTS
        if _TTS is None:
            from core.routage import mode_actuel

            m = mode_actuel()
            moteur = (reglage("tts.engine", "auto") or "auto").lower()
            if m == "local":
                if moteur in {"auto", "elevenlabs"}:
                    moteur = (
                        reglage("tts.fallback_engine", "piper") or "piper"
                    ).lower()
            else:
                if moteur == "auto":
                    moteur = "elevenlabs"
            if moteur == "elevenlabs":
                _TTS = ElevenLabsProvider()
            elif moteur == "chatterbox":
                from services.tts.chatterbox import ChatterboxProvider

                _TTS = ChatterboxProvider()
            elif moteur == "piper":
                _TTS = PiperProvider()
            else:
                _TTS = WindowsProvider()
            LOG.info("provider TTS : %s (mode %s)", _TTS.nom, m)
        return _TTS


def reinitialiser():
    with _LOCK:
        """Force la reconstruction du provider TTS au prochain tts() (switch de mode)."""
        global _TTS
        ancien, _TTS = _TTS, None
        fermer = getattr(ancien, "fermer", None)
        if fermer:
            fermer()
