class Bloc:
    """Imite un bloc de contenu Anthropic (text ou tool_use)."""

    def __init__(self, type, text=None, id=None, name=None, input=None):
        self.type = type
        self.text = text
        self.id = id
        self.name = name
        self.input = input


class Reponse:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


class ProviderLLM:
    nom = "?"

    def respond(self, system, history, tools, context):
        from core.contexte import use

        with use(context):
            return self.repondre(system, history, tools)

    def disponible(self):
        return True

    def repondre(self, systeme, historique, outils):
        raise NotImplementedError
