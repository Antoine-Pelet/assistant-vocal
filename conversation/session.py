from dataclasses import dataclass, field
from core.contexte import ExecutionContext


@dataclass
class ConversationSession:
    context: ExecutionContext
    history: list = field(default_factory=list)
    system: str = ""
    memory_signature: object = None
