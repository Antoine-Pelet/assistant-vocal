"""Appareils logiques et pièces, indépendants des technologies domotiques."""
from dataclasses import dataclass
from typing import Protocol

from core.contexte import ExecutionContext, current
from core.evenements import Event, EventPublisher
from core.util import sans_accents


class DeviceError(ValueError):
    pass


@dataclass(frozen=True)
class Device:
    id: str
    kind: str
    integration: str
    address: str
    capabilities: frozenset[str]
    name: str = ""
    room_id: str | None = None


class DeviceIntegration(Protocol):
    def execute(self, device: Device, action: str, parameters: dict,
                context: ExecutionContext) -> bool: ...


def _norm(value):
    return " ".join(sans_accents(str(value)).lower().split())


class Devices:
    def __init__(self, devices=(), rooms=None, integrations=None,
                 events: EventPublisher | None = None, legacy_resolver=None):
        self._devices = {d.id: d for d in devices}
        self._rooms = rooms or {}
        self._integrations = dict(integrations or {})
        self._events = events
        self._legacy_resolver = legacy_resolver

    def register_integration(self, name, adapter):
        self._integrations[name] = adapter

    def get(self, device_id):
        try:
            return self._devices[device_id]
        except KeyError:
            raise DeviceError(f"Appareil non configuré : {device_id}.") from None

    def resolve(self, target, kind="light", context=None):
        context = context if context is not None else current()
        if target in self._devices:
            device = self.get(target)
            if device.kind != kind:
                raise DeviceError("Cet appareil ne correspond pas à cette commande.")
            return device
        if _norm(target) in {"", "ici", "cette piece", "la piece", "cette pièce"}:
            if not context.room_id:
                raise DeviceError("Dans quelle pièce ? La pièce de cet appareil n'est pas configurée.")
            target = context.room_id
        for room_id, room in self._rooms.items():
            if _norm(target) in {_norm(room_id), _norm(room.get("name", room_id)),
                                 _norm("le " + room_id), _norm("la " + room_id)}:
                device_id = (room.get("devices") or {}).get(kind)
                if not device_id:
                    raise DeviceError(f"Aucun appareil {kind} associé à la pièce {room_id}.")
                device = self.get(device_id)
                if device.kind != kind:
                    raise DeviceError("Type d'appareil incompatible avec la pièce.")
                return device
        if self._legacy_resolver:
            device = self._legacy_resolver(str(target), kind)
            if device is not None:
                return device
        raise DeviceError(f"Pièce ou appareil inconnu : {target}.")

    def perform(self, device, action, parameters=None, context=None):
        context = context if context is not None else current()
        device = self.get(device) if isinstance(device, str) else device
        if action not in device.capabilities:
            raise DeviceError(f"Action {action} non disponible sur {device.name or device.id}.")
        adapter = self._integrations.get(device.integration)
        if adapter is None:
            raise DeviceError(f"Intégration non installée : {device.integration}.")
        try:
            ok = adapter.execute(device, action, dict(parameters or {}), context)
        except DeviceError:
            raise
        except Exception:
            raise DeviceError("L'appareil est injoignable.") from None
        if not ok:
            raise DeviceError("L'appareil a refusé la commande.")
        if self._events:
            self._events.publish(Event.create("device.command_completed",
                {"target_device_id": device.id, "action": action}, context))
        return device

    def select(self, target, kind="light", context=None):
        if _norm(target) in {"toutes", "tout", "toute", "partout", "toutes les pieces",
                             "toutes les lumieres", "la maison", "maison"}:
            matches = [device for device in self._devices.values() if device.kind == kind]
            if matches:
                return matches
        return [self.resolve(target, kind, context)]

    def turn_on(self, device_id, context=None):
        return self.perform(device_id, "turn_on", context=context)

    def turn_off(self, device_id, context=None):
        return self.perform(device_id, "turn_off", context=context)


def turn_on(device_id, context=None):
    from core.maison import devices
    return devices().turn_on(device_id, context)


def turn_off(device_id, context=None):
    from core.maison import devices
    return devices().turn_off(device_id, context)
