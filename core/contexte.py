"""Origine d'une exécution. Ce contexte de routage n'accorde aucun droit d'accès."""
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from dataclasses import asdict, dataclass, field
from functools import wraps
from uuid import uuid4


@dataclass(frozen=True)
class ExecutionContext:
    user_id: str = "local"
    session_id: str = field(default_factory=lambda: uuid4().hex)
    room_id: str | None = None
    device_id: str | None = "main_pc"
    satellite_id: str | None = None
    source: str = "local"

    def to_dict(self):
        return asdict(self)


_CURRENT = ContextVar("red_execution_context", default=None)
_LOCAL_SESSION = uuid4().hex


def current() -> ExecutionContext:
    contexte = _CURRENT.get()
    if contexte is not None:
        return contexte
    from core.config import reglage
    return ExecutionContext(
        user_id=str(reglage("execution.user_id", "local") or "local"),
        session_id=_LOCAL_SESSION,
        room_id=reglage("execution.room_id") or None,
        device_id=str(reglage("execution.device_id", "main_pc") or "main_pc"),
    )


@contextmanager
def use(context: ExecutionContext):
    if not isinstance(context, ExecutionContext):
        raise TypeError("ExecutionContext requis.")
    token = _CURRENT.set(context)
    try:
        yield context
    finally:
        _CURRENT.reset(token)


def contextual(function):
    """Ajoute un argument context= facultatif sans toucher aux signatures métier."""
    @wraps(function)
    def wrapped(*args, context=None, **kwargs):
        with use(context if context is not None else current()):
            return function(*args, **kwargs)
    return wrapped


def bind(function):
    """Capturer AVANT Thread.start ; utiliser une liaison neuve pour chaque tâche."""
    snapshot = copy_context()
    return lambda *args, **kwargs: snapshot.run(function, *args, **kwargs)
