class ProviderTTS:
    nom = "?"

    def synthesize(self, text, context):
        from core.contexte import use
        from services import AudioData

        with use(context):
            result = self.synthetiser(text)
        if result is None:
            return None
        import numpy as np

        samples, frequency = result
        return AudioData(np.asarray(samples, dtype="<i2").tobytes(), int(frequency))

    def disponible(self):
        return True

    def synthetiser(self, texte):
        """Renvoie (numpy int16 mono, frequence_hz) ou None si indisponible."""
        return None
