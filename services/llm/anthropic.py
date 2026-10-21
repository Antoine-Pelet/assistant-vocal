import json
import logging
from core.config import reglage
from core import cloud
from services.llm.models import Bloc, Reponse, ProviderLLM

LOG = logging.getLogger("assistant.llm")


class ClaudeProvider(ProviderLLM):
    nom = "Claude"

    def __init__(self, modele=None):
        import anthropic

        cle = reglage("anthropic.cle", "")
        self.modele = modele or reglage("anthropic.modele", "claude-haiku-4-5")
        self.client = anthropic.Anthropic(api_key=cle) if cle else None

    def disponible(self):
        return self.client is not None

    def repondre(self, systeme, historique, outils):
        # La reponse native Anthropic a deja la bonne forme (.stop_reason/.content).
        kwargs = {
            "model": self.modele,
            "max_tokens": 1024,
            "system": [
                {
                    "type": "text",
                    "text": systeme,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": historique,
        }
        if outils:
            kwargs["tools"] = outils
        rep = self.client.messages.create(**kwargs)
        # Comptabilite (N9) : tokens + cout estime, par jour, cote Red.
        try:
            u = getattr(rep, "usage", None)
            if u is not None:
                from core import budget

                budget.enregistrer(
                    "Claude (Red)",
                    self.modele,
                    getattr(u, "input_tokens", 0) or 0,
                    getattr(u, "output_tokens", 0) or 0,
                    cache_read=getattr(u, "cache_read_input_tokens", 0) or 0,
                    cache_creation=getattr(u, "cache_creation_input_tokens", 0) or 0,
                )
        except Exception:
            pass
        return rep
