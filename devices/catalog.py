"""Composition locale : associe le catalogue logique aux pilotes disponibles."""

from core.config import reglage
from core.devices import Device, DeviceError, Devices
from core.evenements import bus
from integrations.hue import HueIntegration, charger_pieces_hue
import json
from threading import RLock

_HUE = HueIntegration()
_ADAPTERS = {"hue": _HUE}
LIGHT_ACTIONS = frozenset({"turn_on", "turn_off", "set_brightness", "set_color"})
_CACHE = None
_CACHE_KEY = None
_LOCK = RLock()


def register_integration(name, adapter):
    """Point de composition, appelé au démarrage ; aucune importation dynamique depuis YAML."""
    _ADAPTERS[name] = adapter
    invalidate()


def invalidate():
    global _CACHE, _CACHE_KEY
    with _LOCK:
        _CACHE = None
        _CACHE_KEY = None


def devices():
    global _CACHE, _CACHE_KEY
    key = json.dumps(
        [reglage("rooms", {}), reglage("devices", {})],
        sort_keys=True,
        ensure_ascii=False,
    )
    with _LOCK:
        if _CACHE is None or key != _CACHE_KEY:
            _CACHE = _build()
            _CACHE_KEY = key
        return _CACHE


def _build():
    rooms = reglage("rooms", {}) or {}
    configured = reglage("devices", {}) or {}
    if not isinstance(rooms, dict) or not isinstance(configured, dict):
        raise DeviceError("rooms et devices doivent être des dictionnaires.")
    entries = []
    for ident, definition in configured.items():
        if not isinstance(definition, dict):
            raise DeviceError(f"Configuration invalide de l'appareil {ident}.")
        kind = definition.get("kind", "light")
        adapter, address = definition.get("integration"), definition.get("address")
        if not isinstance(adapter, str) or not isinstance(address, str) or not address:
            raise DeviceError(f"Intégration et adresse requises pour {ident}.")
        capabilities = definition.get(
            "capabilities", LIGHT_ACTIONS if kind == "light" else ()
        )
        if not isinstance(capabilities, (list, tuple, set, frozenset)):
            raise DeviceError(f"Liste de capacités invalide pour {ident}.")
        entries.append(
            Device(
                ident,
                kind,
                adapter,
                address,
                frozenset(capabilities),
                definition.get("name", ident),
                definition.get("room_id"),
            )
        )
    for room_id, room in rooms.items():
        if not isinstance(room, dict) or not isinstance(room.get("devices", {}), dict):
            raise DeviceError(f"Configuration invalide de la pièce {room_id}.")
    return Devices(entries, rooms, _ADAPTERS, bus, _HUE.resolve_legacy)


def room_for_satellite(satellite_id, fallback=None):
    matches = [
        room_id
        for room_id, room in (reglage("rooms", {}) or {}).items()
        if isinstance(room, dict) and room.get("satellite") == satellite_id
    ]
    if len(matches) > 1:
        raise DeviceError("Ce satellite est associé à plusieurs pièces.")
    return matches[0] if matches else fallback


def charger_appareils():
    # Compatibilité : la découverte Hue préexistante ne change pas de protocole.
    if reglage("hue.pont") and reglage("hue.cle"):
        charger_pieces_hue()
