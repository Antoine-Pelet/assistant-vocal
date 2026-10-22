"""Pont de migration : les outils existants restent à leur emplacement."""
from core.module import RedModule
from core.legacy_tools import LegacyToolAdapter
from . import routing


class Module(RedModule):
    def register(self, app):
        from core import registre
        registre.charger_outils(exclude=app.capabilities.claimed_tool_modules)
        self.app = app
        app.capabilities.legacy = LegacyToolAdapter(app.capabilities)
        app.route(lambda text, ctx: routing.decider_prioritaire(text, ctx.room_id or ""), priority=10)
        app.route(lambda text, ctx: routing.decider_media(text, ctx.room_id or ""), priority=40)
        app.select_domains(routing.modules_pour_phrase)
        app.subscribe("audio.ready", self.attach_audio)

    def attach_audio(self, event):
        if getattr(self, "audio_attached", False):
            return
        endpoint = self.app.capabilities.require(event.payload["capability"])
        self.audio_attached = True
        from .startup import attach
        attach(self.app, endpoint)
