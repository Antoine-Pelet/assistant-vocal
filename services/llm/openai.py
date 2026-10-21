import json
import logging
from core.config import reglage
from core import cloud
from services.llm.models import Bloc, Reponse, ProviderLLM

LOG = logging.getLogger("assistant.llm")


class OpenAIProvider(ProviderLLM):
    """Adaptateur Responses API -> forme historique comprise par jarvis14."""

    nom = "OpenAI"

    def __init__(self, modele=None, qualite=False):
        self.modele = modele or cloud.modele(qualite=qualite)
        self.qualite = qualite
        self.client = cloud.client_openai()

    def disponible(self):
        return self.client is not None

    @staticmethod
    def _outils(outils):
        return [
            {
                "type": "function",
                "name": o["name"],
                "description": o.get("description", ""),
                "parameters": o.get(
                    "input_schema", {"type": "object", "properties": {}}
                ),
                "strict": False,
            }
            for o in outils
        ]

    @staticmethod
    def _contenu_image(contenu):
        for item in contenu or []:
            if not isinstance(item, dict) or item.get("type") != "image":
                continue
            src = item.get("source", {}) or {}
            if src.get("type") == "base64" and src.get("data"):
                mime = src.get("media_type", "image/jpeg")
                return f"data:{mime};base64,{src['data']}"
        return ""

    def _traduire(self, historique):
        """Historique Anthropic interne -> items Responses API."""
        items = []
        for message in historique:
            role = message.get("role", "user")
            contenu = message.get("content", "")
            if isinstance(contenu, str):
                items.append({"role": role, "content": contenu})
                continue

            if role == "assistant":
                textes = [
                    b.text
                    for b in (contenu or [])
                    if getattr(b, "type", None) == "text" and b.text
                ]
                if textes:
                    items.append({"role": "assistant", "content": " ".join(textes)})
                for bloc in contenu or []:
                    if getattr(bloc, "type", None) != "tool_use":
                        continue
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": bloc.id,
                            "name": bloc.name,
                            "arguments": json.dumps(
                                bloc.input or {}, ensure_ascii=False
                            ),
                        }
                    )
                continue

            # Les resultats d'outils sont des items autonomes. Une capture est
            # ajoutee comme image utilisateur juste apres son function output.
            for resultat in contenu or []:
                if (
                    not isinstance(resultat, dict)
                    or resultat.get("type") != "tool_result"
                ):
                    continue
                sortie = resultat.get("content", "")
                image = self._contenu_image(sortie) if isinstance(sortie, list) else ""
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": resultat.get("tool_use_id", ""),
                        "output": (
                            "Capture d'ecran disponible." if image else str(sortie)
                        ),
                    }
                )
                if image:
                    items.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_image",
                                    "image_url": image,
                                }
                            ],
                        }
                    )
        return items

    def repondre(self, systeme, historique, outils):
        kwargs = {
            "model": self.modele,
            "instructions": systeme,
            "input": self._traduire(historique),
            "max_output_tokens": int(reglage("openai.max_output_tokens", 2048)),
            "store": False,
        }
        outils_api = self._outils(outils)
        if outils_api:
            kwargs["tools"] = outils_api
            kwargs["parallel_tool_calls"] = True
        raisonnement = cloud._raisonnement(self.modele, self.qualite)
        if raisonnement:
            kwargs["reasoning"] = raisonnement
        rep = self.client.responses.create(**kwargs)
        cloud.enregistrer_usage(rep, "OpenAI (Red)", self.modele)

        blocs = []
        texte = (getattr(rep, "output_text", "") or "").strip()
        if texte:
            blocs.append(Bloc("text", text=texte))
        for item in getattr(rep, "output", []) or []:
            if getattr(item, "type", None) != "function_call":
                continue
            brut = getattr(item, "arguments", "{}") or "{}"
            try:
                arguments = json.loads(brut) if isinstance(brut, str) else dict(brut)
            except (ValueError, TypeError):
                LOG.warning("OpenAI: arguments outil invalides (%s)", brut)
                arguments = {}
            blocs.append(
                Bloc(
                    "tool_use",
                    id=getattr(item, "call_id", None) or getattr(item, "id", None),
                    name=getattr(item, "name", ""),
                    input=arguments,
                )
            )
        stop = "tool_use" if any(b.type == "tool_use" for b in blocs) else "end"
        return Reponse(stop, blocs)
