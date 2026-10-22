from core.module import RedModule
from core.capabilities import CapabilityRequest


class Module(RedModule):
    def register(self, app):
        from core import registre
        from tools import deleguer_a_hermes as engine
        self.engine = engine
        app.on_stop(engine.suspendre_retours)
        app.adopt_tool(registre.get("deleguer_a_hermes"), name="hermes.delegate",
                       intents=("fais une recherche de fond",))
        app.adopt_tool(registre.get("taches_hermes"), name="hermes.tasks")
        app.capability(self.content, name="hermes.create_content",
            description="Confie un travail de contenu à Hermes et annonce le résultat.",
            arguments={"type":"object", "properties":{"tache":{"type":"string"}}, "required":["tache"]})
        app.route(self.route, priority=50)

    def content(self, tache):
        return self.engine.deleguer_en_fond(tache, intro="Hermes a terminé le travail de contenu. ", nom_thread="contenu-hermes")

    def route(self, phrase, context):
        task = self.engine.extraire_tache_contenu(phrase)
        if task is not None:
            return CapabilityRequest("hermes.create_content", {"tache":task})
