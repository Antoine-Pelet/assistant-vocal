"""Conversion PCM via les services partagés ; aucune conversation ici."""

import logging
import threading
from .protocol import TAUX

LOG = logging.getLogger("assistant.satellite.audio")


def _transcrire(pcm_bytes, context=None):
    """PCM 16-bit LE mono 16 kHz -> texte (faster-whisper, modèle partagé lazy)."""
    from core.contexte import current
    from services import AudioData
    from services.stt.faster_whisper import WhisperService

    if len(pcm_bytes) < TAUX * 2 * 0.3:
        return ""
    modele = _whisper()
    if modele is None:
        return ""
    return WhisperService(modele).transcribe(
        AudioData(bytes(pcm_bytes), TAUX), context or current()
    )


_WHISPER = None


def _whisper():
    from services.stt.faster_whisper import model

    try:
        return model()
    except Exception:
        LOG.exception("satellite: chargement STT")
        return None


def _tts_pcm(texte, context=None):
    """Synthétise `texte` -> (pcm_bytes 16-bit LE mono, frequence_hz) ou (b"", 0)."""
    try:
        from core.tts import tts
        from core.contexte import current
        from services.tts.base import ProviderTTS

        audio = ProviderTTS.synthesize(tts(), texte, context or current())
        return (audio.pcm, audio.sample_rate) if audio else (b"", 0)
    except Exception:
        LOG.exception("satellite: TTS")
        return b"", 0


_TTS_COURT = {}
_TTS_COURT_LOCK = threading.Lock()


def _tts_pcm_court(texte, context=None):
    """TTS mis en cache pour les accusés répétés du satellite.

    Le premier passage utilise le moteur vocal configuré ; les suivants évitent
    un nouvel appel cloud et partent presque immédiatement.
    """
    with _TTS_COURT_LOCK:
        from core.config import reglage

        key = (
            texte,
            reglage("tts.engine"),
            reglage("tts.profile"),
            reglage("piper.profile"),
        )
        if key in _TTS_COURT:
            return _TTS_COURT[key]
        resultat = _tts_pcm(texte, context)
        if resultat[0]:
            _TTS_COURT[key] = resultat
        return resultat
