"""Journalisation des appels d'outils et des erreurs vers logs/red.log."""

import logging
from pathlib import Path


class ContextFilter(logging.Filter):
    def filter(self, record):
        from core.contexte import current

        context = current()
        for key in ("session_id", "room_id", "satellite_id", "source"):
            setattr(record, key, getattr(context, key, None) or "-")
        return True


_LOG = None
DOSSIER = Path(__file__).resolve().parents[1] / "logs"


def obtenir():
    """Renvoie le logger 'assistant' (le configure une seule fois)."""
    global _LOG
    if _LOG is None:
        DOSSIER.mkdir(exist_ok=True)
        handler = logging.FileHandler(DOSSIER / "red.log", encoding="utf-8")
        handler.addFilter(ContextFilter())
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(source)s session=%(session_id)s room=%(room_id)s satellite=%(satellite_id)s] %(message)s",
                "%Y-%m-%d %H:%M:%S",
            )
        )
        _LOG = logging.getLogger("assistant")
        _LOG.setLevel(logging.INFO)
        _LOG.handlers.clear()
        _LOG.addHandler(handler)
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        _LOG.addHandler(console)
        _LOG.propagate = False
    return _LOG
