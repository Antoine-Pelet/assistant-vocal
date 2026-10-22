from core.module import RedModule
from core.capabilities import CapabilityRequest


class Module(RedModule):
    def register(self, app):
        from core import registre
        from tools import astra_pc
        self.extract = astra_pc.extraire_commande_explicite
        self.settings = app.settings
        app.adopt_tool(registre.get("controle_pc_astra"), name="computer.execute_action",
                       intents=("Utilise Astra pour ouvrir les paramètres audio",))
        app.route(self.route, priority=20)

    def route(self, phrase, context):
        task = self.extract(phrase)
        if task is not None:
            return CapabilityRequest("computer.execute_action", {"tache":task})

    def health(self):
        return {"ok": True, "detail": "Chaque prise de contrôle exige une confirmation N3. Le moteur nécessite la configuration OpenAI existante."}
