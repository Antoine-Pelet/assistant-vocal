import json
import logging
from core.config import reglage
from core import cloud
from services.llm.models import Bloc, Reponse, ProviderLLM

LOG = logging.getLogger("assistant.llm")


class OllamaProvider(ProviderLLM):
    nom = "Ollama"

    def __init__(self):
        self.hote = reglage("ollama.hote", "http://localhost:11434").rstrip("/")
        self.modele = reglage("ollama.modele", "qwen3.5:4b")

    def disponible(self):
        try:
            import requests

            r = requests.get(f"{self.hote}/api/tags", timeout=3)
            r.raise_for_status()
            nom = self.modele if ":" in self.modele else self.modele + ":latest"
            return any(
                m.get("name") == nom or m.get("model") == nom
                for m in r.json().get("models", [])
            )
        except Exception:
            return False

    # -- traduction historique Anthropic -> messages Ollama --
    def _traduire(self, systeme, historique):
        messages = [{"role": "system", "content": systeme}]
        for m in historique:
            role, contenu = m.get("role"), m.get("content")
            if role == "user":
                if isinstance(contenu, str):
                    messages.append({"role": "user", "content": contenu})
                else:
                    for item in contenu or []:
                        if not isinstance(item, dict):
                            continue
                        if item.get("type") == "tool_result":
                            c = item.get("content")
                            if isinstance(c, list):  # bloc image
                                c = "[image capturee — la vision n'est pas disponible en mode local]"
                            messages.append({"role": "tool", "content": str(c)})
                        elif item.get("type") == "image":
                            messages.append(
                                {
                                    "role": "user",
                                    "content": "[image — vision indisponible en local]",
                                }
                            )
            else:  # assistant
                if isinstance(contenu, str):
                    messages.append({"role": "assistant", "content": contenu})
                else:
                    texte = " ".join(
                        b.text
                        for b in (contenu or [])
                        if getattr(b, "type", None) == "text" and b.text
                    )
                    appels = [
                        b
                        for b in (contenu or [])
                        if getattr(b, "type", None) == "tool_use"
                    ]
                    msg = {"role": "assistant", "content": texte}
                    if appels:
                        msg["tool_calls"] = [
                            {"function": {"name": b.name, "arguments": b.input or {}}}
                            for b in appels
                        ]
                    messages.append(msg)
        return messages

    def _outils(self, outils):
        return [
            {
                "type": "function",
                "function": {
                    "name": o["name"],
                    "description": o["description"],
                    "parameters": o.get(
                        "input_schema", {"type": "object", "properties": {}}
                    ),
                },
            }
            for o in outils
        ]

    def _chat(self, messages, tools, nudge=None):
        import requests

        if nudge:
            messages = messages + [{"role": "user", "content": nudge}]
        # think=false : desactive le "raisonnement" natif (qwen3.5, etc.). Sinon le
        # modele est tres lent et rend parfois ses appels d'outils en texte au lieu
        # de les executer. Un modele sans thinking ignore ce parametre.
        corps = {
            "model": self.modele,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "think": bool(reglage("ollama.think", False)),
            "options": {
                "temperature": 0.3,
                "num_ctx": int(reglage("ollama.num_ctx", 4096)),
                "num_predict": int(reglage("ollama.num_predict", 256)),
            },
        }
        if not tools:
            corps.pop("tools")
        r = requests.post(f"{self.hote}/api/chat", timeout=120, json=corps)
        r.raise_for_status()
        return r.json()

    def _parser(self, rep):
        msg = rep.get("message", {}) or {}
        blocs = []
        texte = (msg.get("content") or "").strip()
        if texte:
            blocs.append(Bloc("text", text=texte))
        for i, tc in enumerate(msg.get("tool_calls") or []):
            fn = tc.get("function", {}) or {}
            args = fn.get("arguments", {})
            if isinstance(args, str):
                args = json.loads(args)  # peut lever -> gere par le retry
            blocs.append(
                Bloc("tool_use", id=f"call_{i}", name=fn.get("name"), input=args or {})
            )
        stop = "tool_use" if any(b.type == "tool_use" for b in blocs) else "end"
        return Reponse(stop, blocs)

    def repondre(self, systeme, historique, outils):
        messages = self._traduire(systeme, historique)
        tools = self._outils(outils)
        try:
            return self._parser(self._chat(messages, tools))
        except Exception as e:
            LOG.warning("ollama: 1er essai en echec (%s), retry plus directif", e)
            # Retry unique, avec une consigne plus stricte sur l'appel d'outil.
            nudge = (
                "Rappel : pour agir, appelle l'outil approprie via un tool call "
                "avec des arguments JSON valides ; sinon reponds simplement en texte."
            )
            try:
                return self._parser(self._chat(messages, tools, nudge=nudge))
            except Exception:
                LOG.exception("ollama: echec apres retry")
                return Reponse(
                    "end",
                    [
                        Bloc(
                            "text",
                            text=(
                                "Desole, le modele local n'a pas reussi a traiter la demande "
                                "correctement. Reessaie en reformulant, ou repasse en mode cloud."
                            ),
                        )
                    ],
                )
