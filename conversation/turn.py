from dataclasses import dataclass, field
from core.contexte import ExecutionContext, current


@dataclass(frozen=True)
class ConversationTurn:
    text: str
    context: ExecutionContext = field(default_factory=current)
    speaker_id: str | None = None
    speaker_confidence: float | None = None
    transcription_confidence: float | None = None

    @property
    def session_id(self):
        return self.context.session_id

    @property
    def room_id(self):
        return self.context.room_id

    @property
    def device_id(self):
        return self.context.device_id

    @property
    def satellite_id(self):
        return self.context.satellite_id

    @property
    def source(self):
        return self.context.source
