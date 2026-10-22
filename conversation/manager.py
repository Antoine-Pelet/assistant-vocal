"""Orchestration commune : prompt, mémoire, LLM, outils et confirmation.

Aucun microphone, haut-parleur, WebSocket ni interface graphique ici.
"""

import logging
import time
from threading import RLock
from core import config, memoire, registre
from core.contexte import current, use
from core.util import nettoyer_reponse_vocale
from services.llm.models import ProviderLLM
from conversation.session import ConversationSession
from conversation.prompt import build

LOG = logging.getLogger("assistant.conversation")
SENTINEL_CONFIRM = "\x00confirmation\x00"


class Output:
    def __init__(self, manager, session):
        self.manager, self.session = manager, session

    def say(self, text, interruptible=True):
        pass

    def event(self, *args):
        pass

    def cancelled(self):
        return False

    def last_tool(self, name):
        pass

    def execute(self, blocks):
        return self.manager.execute_tools(self.session, blocks, self)

    def priority(self, history):
        return self.manager.priority(self.session, history, self)


class ConversationManager:
    def close_all(self):
        with self._lock:
            for session in list(self._sessions.values()):
                self.close(session.context)

    def __init__(self):
        self._sessions = {}
        self._lock = RLock()

    def session(self, context=None, history=None):
        context = context or current()
        key = (
            context.source,
            context.session_id,
            context.device_id,
            context.satellite_id,
        )
        with self._lock:
            s = self._sessions.setdefault(key, ConversationSession(context))
            s.context = context
            if history is not None:
                s.history = history
            return s

    def close(self, context):
        from security.confirmations import annuler_confirme

        key = (
            context.source,
            context.session_id,
            context.device_id,
            context.satellite_id,
        )
        with use(context):
            annuler_confirme()
        with self._lock:
            s = self._sessions.pop(key, None)
            if s:
                s.history.clear()
                s.system = ""
                s.memory_signature = None

    def refresh(self, session, protected=False):
        # Une ouverture locale d'une zone n'autorise pas sa diffusion aux satellites.
        protected = protected and session.context.source == "local"
        signature, facts = memoire.contexte(protegees=protected)
        signature = (bool(protected), signature)
        if (
            session.memory_signature is not None
            and signature != session.memory_signature
        ):
            last = next(
                (
                    m
                    for m in reversed(session.history)
                    if m.get("role") == "user" and isinstance(m.get("content"), str)
                ),
                None,
            )
            session.history[:] = [last] if last else []
        session.memory_signature = signature
        session.system = build(facts, session.context)
        return signature

    def handle(self, turn, history=None, output=None):
        with use(turn.context):
            session = self.session(turn.context, history)
            session.history.append({"role": "user", "content": turn.text})
            if len(session.history) > 40:
                del session.history[:-40]
                while session.history and not (
                    session.history[0].get("role") == "user"
                    and isinstance(session.history[0].get("content"), str)
                ):
                    session.history.pop(0)
            output = output or Output(self, session)
            text = self.respond(session, output)
            if text == SENTINEL_CONFIRM:
                return {
                    "reponse": (registre.annonce_en_attente() or "")
                    + " Tu confirmes ?",
                    "attente_confirmation": True,
                }
            return {"reponse": text, "attente_confirmation": False}

    def execute_tools(self, session, blocs, output):
        """Execute les outils demandes par le LLM actif et renvoie leurs resultats.

        S'appuie sur le registre. Logge chaque appel, ne crashe jamais (une
        exception d'outil devient une reponse comprehensible), et met les outils a
        confirmation en attente au lieu de les executer tout de suite.
        """
        resultats = []
        for bloc in blocs:
            if getattr(bloc, "type", None) != "tool_use":
                continue
            if output.cancelled():
                break
            nom = bloc.name
            arguments = bloc.input or {}
            debut_outil = time.monotonic()
            from assistant_vocal.runtime import runtime
            from core.capability_errors import CapabilityExecutionError
            runtime.start()
            try:
                resultat = runtime.capabilities.execute(nom, arguments)
            except CapabilityExecutionError as error:
                resultat = str(error)

            LOG.info(
                "outil %s termine en %.3fs (type=%s)",
                nom,
                time.monotonic() - debut_outil,
                type(resultat).__name__,
            )
            output.last_tool(nom)

            # Cas image (capture d'ecran) : bloc image dans le tool_result.
            if isinstance(resultat, dict) and resultat.get("image"):
                img = resultat["image"]
                apercu = resultat.get("apercu", "Capture d'ecran envoyee.")
                LOG.info("Résultat visuel : %s", nom)
                output.event("outil", nom, apercu[:60])
                contenu = [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img["media_type"],
                            "data": img["data"],
                        },
                    }
                ]
            else:
                LOG.info("Action terminée : %s", nom)
                output.event("outil", nom, "Action terminee")
                contenu = str(resultat)

            resultats.append(
                {
                    "type": "tool_result",
                    "tool_use_id": bloc.id,
                    "content": contenu,
                }
            )

        return resultats

    def priority(self, session, historique, output):
        """Exécute la décision commune au micro principal et aux satellites.

        La détection vit dans ``core.routage_intentions`` ; cette fonction ne garde
        que les détails propres au poste principal (HUD, voix et registre global de
        confirmation).
        """
        question = next(
            (
                m.get("content")
                for m in reversed(historique)
                if m.get("role") == "user" and isinstance(m.get("content"), str)
            ),
            "",
        )
        from core.routage_intentions import decider_prioritaire

        decision = decider_prioritaire(question, piece=current().room_id or "")
        if decision is None:
            return None

        return self.execute_decision(session, decision, output, question)

    def execute_decision(self, session, decision, output, question=""):
        historique = session.history
        nom_outil = decision.outil
        from types import SimpleNamespace
        bloc = SimpleNamespace(type="tool_use", name=nom_outil,
                               input=decision.arguments, id="route-prioritaire-commune")
        resultats = output.execute([bloc])
        annonce = registre.annonce_en_attente()
        if annonce:
            output.event("etat", "parole")
            if not output.cancelled():
                output.say(annonce + " Tu confirmes ?", interruptible=False)
            return SENTINEL_CONFIRM
        texte = str(resultats[0]["content"] if resultats else "C'est fait.")

        historique.append({"role": "assistant", "content": texte})
        output.event("outil", nom_outil, question[:60])
        output.event("etat", "parole")
        if texte and not output.cancelled():
            output.say(texte)
        return texte

    def respond(self, session, output):
        """Interroge le LLM actif et boucle sur les appels d'outils jusqu'a la reponse.

        L’accusé commun est lancé par repondre(). Pour
        les outils a confirmation, prononce l'annonce et renvoie SENTINEL_CONFIRM
        (la suite est geree par traiter, qui capture la reponse oui/non).
        """
        historique = session.history
        prioritaire = output.priority(historique)
        if prioritaire is not None:
            return prioritaire

        from core.llm import llm

        fournisseur = llm()
        if not fournisseur.disponible():
            mode = config.reglage("mode", "cloud")
            if mode == "local":
                return (
                    "Le modele local (Ollama) n'est pas joignable. Verifie qu'Ollama "
                    "tourne et que le modele est telecharge."
                )
            from core import cloud

            return (
                "Ma cle OpenAI n'est pas configuree."
                if cloud.fournisseur() == "openai"
                else "Ma cle Anthropic n'est pas configuree."
            )

        question = next(
            (
                m.get("content")
                for m in reversed(historique)
                if m.get("role") == "user" and isinstance(m.get("content"), str)
            ),
            "",
        )
        from assistant_vocal.runtime import runtime
        runtime.start()
        modules_outils = runtime.capabilities.select_domains(question)
        max_tours_outils = max(
            1, min(int(config.reglage("assistant.max_tours_outils", 6) or 6), 12)
        )
        max_appels_outils = max(
            1, min(int(config.reglage("assistant.max_appels_outils", 12) or 12), 30)
        )
        timeout_tour = max(
            15.0,
            min(float(config.reglage("assistant.timeout_tour", 120) or 120), 300.0),
        )
        debut_tour = time.monotonic()
        appels_outils = 0

        def arreter_tour(texte):
            """Clôt proprement une erreur/limite et la rend audible."""
            historique.append({"role": "assistant", "content": texte})
            output.event("etat", "parole")
            if texte and not output.cancelled():
                output.say(texte)
            return texte

        # max_tours_outils tours avec outils, puis un dernier appel autorisé pour
        # formuler la réponse finale à partir des résultats.
        for numero_tour in range(max_tours_outils + 1):
            if output.cancelled():
                return ""
            if time.monotonic() - debut_tour > timeout_tour:
                LOG.warning(
                    "tour LLM interrompu après %.1fs", time.monotonic() - debut_tour
                )
                return arreter_tour(
                    "J'arrête cette demande : elle prend trop de temps."
                )
            try:
                from urllib.parse import urlsplit

                protegees = (
                    config.reglage("mode", "local") == "local"
                    and fournisseur.nom == "Ollama"
                    and urlsplit(str(getattr(fournisseur, "hote", ""))).hostname
                    in ("localhost", "127.0.0.1", "::1")
                )
                signature_memoire = self.refresh(session, protegees)
                debut_llm = time.monotonic()
                reponse = ProviderLLM.respond(
                    fournisseur,
                    session.system,
                    historique,
                    runtime.schemas(
                        local_seulement=(fournisseur.nom == "Ollama"),
                        modules=modules_outils,
                    ),
                    current(),
                )
                LOG.info(
                    "latence LLM %s %.3fs (tour=%s, outils=%s)",
                    fournisseur.nom,
                    time.monotonic() - debut_llm,
                    numero_tour + 1,
                    "tous" if modules_outils is None else len(modules_outils),
                )
            except Exception as e:
                LOG.warning("Fournisseur indisponible : %s", fournisseur.nom)
                LOG.exception("appel LLM en echec")
                return arreter_tour(
                    "Je n'arrive pas a joindre le modele pour le moment."
                )

            if output.cancelled():
                return ""

            if self.refresh(session, protegees) != signature_memoire:
                return arreter_tour(
                    "L'accès à la mémoire a changé pendant ma réponse. Peux-tu répéter ta demande ?"
                )

            if reponse.stop_reason == "tool_use":
                output.event("etat", "reflexion")
                noms = [
                    b.name
                    for b in reponse.content
                    if getattr(b, "type", None) == "tool_use"
                ]
                if (
                    numero_tour >= max_tours_outils
                    or appels_outils + len(noms) > max_appels_outils
                ):
                    LOG.warning(
                        "limite d'outils atteinte (tours=%s, appels=%s, nouveaux=%s)",
                        numero_tour,
                        appels_outils,
                        len(noms),
                    )
                    return arreter_tour(
                        "J'arrête ici pour éviter une boucle d'actions. "
                        "Reformule la tâche plus précisément si tu veux que je continue."
                    )
                appels_outils += len(noms)
                historique.append({"role": "assistant", "content": reponse.content})
                resultats = output.execute(reponse.content)
                historique.append({"role": "user", "content": resultats})

                annonce = registre.annonce_en_attente()
                if annonce:
                    output.event("etat", "parole")
                    phrase = annonce + " Tu confirmes ?"
                    if not output.cancelled():
                        output.say(phrase, interruptible=False)
                    return SENTINEL_CONFIRM
                continue

            # Reponse finale. On attend la fin de l'accuse pour ne pas parler dessus.
            texte = " ".join(
                b.text for b in reponse.content if getattr(b, "type", None) == "text"
            ).strip()
            texte = nettoyer_reponse_vocale(texte)
            historique.append({"role": "assistant", "content": texte})
            output.event("etat", "parole")
            if texte and not output.cancelled():
                output.say(texte)
            return texte

        return arreter_tour(
            "Je n'ai pas réussi à terminer cette demande sans dépasser mes limites."
        )


manager = ConversationManager()
