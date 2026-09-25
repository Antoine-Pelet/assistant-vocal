"""Événements versionnés et bus local éphémère. Aucun réseau ni journal implicite."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from threading import RLock
from typing import Protocol
from uuid import uuid4

from core.contexte import ExecutionContext, current


@dataclass(frozen=True)
class Event:
    name: str
    context: ExecutionContext
    _payload_json: str = field(repr=False)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_id: str = field(default_factory=lambda: uuid4().hex)
    schema_version: int = 1

    @classmethod
    def create(cls, name, payload=None, context=None):
        # Copie JSON : aucun objet Python vivant ni mutation tardive du payload.
        return cls(name, context if context is not None else current(),
                   json.dumps(payload if payload is not None else {},
                              ensure_ascii=False, allow_nan=False))

    @property
    def payload(self):
        return json.loads(self._payload_json)

    def to_dict(self):
        return {"schema_version": self.schema_version, "event_id": self.event_id,
                "type": self.name, **self.context.to_dict(),
                "timestamp": self.timestamp, "payload": self.payload}

    def to_json(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, allow_nan=False)


class EventPublisher(Protocol):
    def publish(self, event: Event) -> None: ...


class LocalEventBus:
    def __init__(self):
        self._callbacks = []
        self._lock = RLock()
        self.delivery_errors = 0

    def subscribe(self, callback):
        with self._lock:
            self._callbacks.append(callback)
        def unsubscribe():
            with self._lock:
                if callback in self._callbacks:
                    self._callbacks.remove(callback)
        return unsubscribe

    def publish(self, event):
        with self._lock:
            callbacks = tuple(self._callbacks)
        for callback in callbacks:
            try:
                callback(event)
            except Exception:
                # Une panne de notification ne doit pas faire rejouer une action physique.
                # Aucun contenu ni traceback d'abonné potentiellement sensible n'est logué.
                with self._lock:
                    self.delivery_errors += 1


bus = LocalEventBus()
