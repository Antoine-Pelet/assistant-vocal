from core.module import RedModule
from core.capabilities import CapabilityRequest
from .intents import est_demande_vision_ecran


class Module(RedModule):
    def register(self, app):
        from core import registre
        from tools.ecran import analyser_ecran
        self.settings = app.settings
        app.adopt_tool(registre.get("capture_screen"), name="vision.capture_screen")
        app.capability(analyser_ecran, name="vision.analyze_screen",
            description="Explique la fenêtre active sans agir sur le PC.",
            arguments={"type":"object", "properties":{"question":{"type":"string"}}, "required":["question"]},
            intents=("lis cette erreur sur mon écran", "décris mon écran"))
        app.route(self.route, priority=30)

    def route(self, phrase, context):
        if est_demande_vision_ecran(phrase):
            return CapabilityRequest("vision.analyze_screen", {"question":phrase})

    def health(self):
        return {"ok": True, "detail": "Analyse indisponible en mode local." if self.settings and self.settings.reglage("mode", "local") == "local" else "Analyse à la demande."}
