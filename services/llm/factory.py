"""Fabrique LLM : un provider courant, SDK cloud importés seulement à l'appel."""

import logging
from threading import RLock

_LOCK = RLock()
from core import cloud
from services.llm.models import Bloc, Reponse, ProviderLLM
from services.llm.ollama import OllamaProvider
from services.llm.openai import OpenAIProvider
from services.llm.anthropic import ClaudeProvider

LOG = logging.getLogger("assistant.llm")
_LLM = None


def llm():
    with _LOCK:
        """Provider LLM courant selon le mode (local | hybride | qualite).

        - local   : Ollama.
        - hybride : cloud economique (OpenAI par defaut) - reflexes + vision.
        - qualite : cloud fort (GPT-6 Astra par defaut)."""
        global _LLM
        if _LLM is None:
            from core.routage import mode_actuel

            m = mode_actuel()
            if m == "local":
                _LLM = OllamaProvider()
            else:
                qualite = m == "qualite"
                if cloud.fournisseur() == "openai":
                    _LLM = OpenAIProvider(
                        cloud.modele(qualite=qualite), qualite=qualite
                    )
                else:
                    _LLM = ClaudeProvider(cloud.modele(qualite=qualite))
            LOG.info(
                "provider LLM : %s (mode %s, modele %s)",
                _LLM.nom,
                m,
                getattr(_LLM, "modele", "-"),
            )
        return _LLM


def reinitialiser():
    with _LOCK:
        """Force la reconstruction du provider au prochain llm() (apres un switch de mode)."""
        global _LLM
        _LLM = None
