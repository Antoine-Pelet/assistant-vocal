"""Contrat local optionnel ; aucun module n'importe la boucle microphone."""
from dataclasses import dataclass
from typing import Callable


@dataclass
class LocalAudioEndpoint:
    transcriber: object
    capture: Callable
    stop_speech: Callable
    feedback: Callable

    def transcribe(self, source, beam_size=1):
        return " ".join(s.text for s in self.transcriber.transcribe(
            source, language="fr", beam_size=beam_size)[0]).strip()
