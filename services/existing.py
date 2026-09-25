"""Adaptation des moteurs existants. Aucun micro, lecteur audio ou transport réseau."""
from core.contexte import use
from services import AudioData


class ExistingSTT:
    def __init__(self, model):
        self.model = model

    def transcribe(self, audio, context):
        import numpy as np
        if audio.sample_rate != 16000 or audio.channels != 1:
            raise ValueError("Whisper attend du PCM mono à 16 kHz.")
        samples = np.frombuffer(audio.pcm, dtype='<i2').astype(np.float32) / 32768.0
        try:
            with use(context):
                segments, _ = self.model.transcribe(samples, language="fr", beam_size=1)
                return " ".join(segment.text for segment in segments).strip()
        finally:
            samples.fill(0)


class ExistingTTS:
    def __init__(self, provider):
        self.provider = provider

    def synthesize(self, text, context):
        with use(context):
            result = self.provider.synthetiser(text)
        if result is None:
            return None  # le repli Windows reste une responsabilité de la sortie locale
        import numpy as np
        samples, frequency = result
        return AudioData(np.asarray(samples, dtype='<i2').tobytes(), int(frequency))


class ExistingLLM:
    def __init__(self, provider):
        self.provider = provider

    def respond(self, system, history, tools, context):
        with use(context):
            return self.provider.repondre(system, history, tools)
