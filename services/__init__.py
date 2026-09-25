"""Contrats des moteurs techniques ; capture et lecture audio restent dans les entrées/sorties."""
from dataclasses import dataclass, field
from typing import Any, Protocol

from core.contexte import ExecutionContext


@dataclass(frozen=True)
class AudioData:
    """PCM signé 16 bits little-endian ; aucune référence à un micro ou haut-parleur."""
    pcm: bytes = field(repr=False)
    sample_rate: int = 16000
    channels: int = 1
    encoding: str = "pcm_s16le"

    def __post_init__(self):
        if (self.encoding != "pcm_s16le" or self.sample_rate <= 0 or self.channels <= 0
                or len(self.pcm) % (2 * self.channels)):
            raise ValueError("Format audio invalide.")


class STTService(Protocol):
    def transcribe(self, audio: AudioData, context: ExecutionContext) -> str: ...


class TTSService(Protocol):
    def synthesize(self, text: str, context: ExecutionContext) -> AudioData | None: ...


class LLMService(Protocol):
    def respond(self, system: str, history: list, tools: list,
                context: ExecutionContext) -> Any: ...


class EmbeddingService(Protocol):
    def embed(self, texts: list[str], context: ExecutionContext) -> list[list[float]]: ...
