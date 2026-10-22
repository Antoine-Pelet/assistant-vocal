from core.module import RedModule


class Module(RedModule):
    def register(self, app):
        self.running = False
        self.events = 0
        self.message = str(app.config.get("message", "pong"))
        app.register_tool(
            self.ping,
            name="demo_ping",
            description="Répond au test local du module de démonstration.",
        )
        app.capability(self.hello, name="demo.hello",
                       description="Salue depuis le module de démonstration.",
                       intents=("bonjour module démo",))
        app.route(self.route)
        app.subscribe("demo.request", self.receive)
        app.publish("demo.ping", self.ping)
        app.admin_endpoint("/health", self.health)

    def hello(self):
        return "Bonjour depuis le module de démonstration."

    def route(self, text, context):
        from core.capabilities import CapabilityRequest
        from core.util import sans_accents
        if sans_accents(text.lower()).strip(" .!?") == "bonjour module demo":
            return CapabilityRequest("demo.hello")

    def ping(self):
        return self.message

    def receive(self, event):
        self.events += 1

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def health(self):
        return {"ok": self.running, "events_received": self.events}
