"""Configuration versionnée ; aliases uniquement ici, écritures atomiques validées."""

from copy import deepcopy
import math
import os
from pathlib import Path
import tempfile
from threading import RLock
import yaml

VERSION = 2
_CONFIG = None
_LOCK = RLock()
_REVISION = 0
FICHIER = Path(__file__).resolve().parent.parent / "config.yaml"
ALIASES = {
    "tts.moteur": "tts.engine",
    "tts.profil": "tts.profile",
    "tts.voix_locale": "piper.profile",
    "assistant.nom": "assistant.name",
    "assistant.personnalite": "assistant.persona",
}


def _get(conf, path, default=None):
    value = conf
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def _set(conf, path, value):
    node = conf
    keys = path.split(".")
    for key in keys[:-1]:
        node = node.setdefault(key, {})
        if not isinstance(node, dict):
            raise ValueError("Section de configuration invalide.")
    node[keys[-1]] = value


def migrate(raw):
    if not isinstance(raw, dict):
        raise ValueError("La configuration doit être un dictionnaire YAML.")
    for section in (
        "assistant",
        "tts",
        "piper",
        "voices",
        "audio",
        "whisper",
        "modules",
        "admin",
        "rooms",
        "devices",
    ):
        if section in raw and not isinstance(raw[section], dict):
            raise ValueError(f"Section {section} invalide.")
    conf = deepcopy(raw)
    version = conf.get("config_version", 1)
    if type(version) is not int or not 1 <= version <= VERSION:
        raise ValueError("Version de configuration non prise en charge.")
    missing = object()
    for old, new in ALIASES.items():
        value = _get(conf, old, missing)
        if value is not missing:
            if _get(conf, new, missing) is missing:
                _set(conf, new, value)
            section, key = old.split(".")
            conf[section].pop(key, None)
    if _get(conf, "assistant.persona") == "jarvis_sarcastique":
        _set(conf, "assistant.persona", "red")
    if _get(conf, "piper.profile") in {"jarvis_fr", "siwis_fr"}:
        _set(conf, "piper.profile", "tom_fr")
    tts = conf.setdefault("tts", {})
    legacy = conf.pop("voix_locale", None)
    conf.pop("kokoro", None)
    tts.setdefault(
        "engine",
        legacy if legacy in {"piper", "chatterbox", "windows"} else "chatterbox",
    )
    if tts["engine"] == "kokoro":
        tts["engine"] = "piper"
    if tts["engine"] == "auto":
        tts["engine"] = "piper" if legacy == "piper" else "chatterbox"
    tts.setdefault("fallback_engine", "piper")
    tts.setdefault("profile", "red")
    conf.setdefault("piper", {}).setdefault("profile", "tom_fr")
    conf.setdefault("assistant", {}).setdefault("name", "Red")
    conf["assistant"].setdefault("persona", "red")
    conf.setdefault("admin", {}).setdefault("enabled", True)
    conf["config_version"] = VERSION
    return conf


def validate(conf):
    if conf.get("config_version") != VERSION:
        raise ValueError("Version de configuration invalide.")
    for section in (
        "assistant",
        "tts",
        "piper",
        "voices",
        "audio",
        "whisper",
        "modules",
        "admin",
        "rooms",
        "devices",
    ):
        if section in conf and not isinstance(conf[section], dict):
            raise ValueError(f"Section {section} invalide.")
    if _get(conf, "tts.engine") not in {"chatterbox", "piper", "windows", "elevenlabs"}:
        raise ValueError("Moteur TTS inconnu.")
    if _get(conf, "tts.fallback_engine") not in {"piper", "windows"}:
        raise ValueError("Le repli vocal doit être local.")
    for path in ("assistant.name", "tts.profile"):
        value = _get(conf, path)
        if not isinstance(value, str) or not value.strip() or len(value) > 120:
            raise ValueError(f"{path} invalide.")
    if type(_get(conf, "admin.enabled")) is not bool:
        raise ValueError("admin.enabled doit être un booléen.")
    for name, settings in conf.get("modules", {}).items():
        if (
            not isinstance(settings, dict)
            or type(settings.get("enabled", False)) is not bool
        ):
            raise ValueError(f"Configuration du module {name} invalide.")
    for ident, voice in conf.get("voices", {}).items():
        if not isinstance(voice, dict):
            raise ValueError(f"Profil vocal {ident} invalide.")
        for key, low, high in [
            ("exaggeration", 0, 2),
            ("cfg_weight", 0, 1),
            ("temperature", 0.05, 2),
        ]:
            value = voice.get(key, 0.5)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not low <= value <= high
            ):
                raise ValueError(f"Paramètre vocal {key} invalide.")
    return conf


def _charger():
    global _CONFIG
    with _LOCK:
        if _CONFIG is None:
            try:
                raw = yaml.safe_load(FICHIER.read_text(encoding="utf8")) or {}
            except FileNotFoundError:
                raw = {}
            except yaml.YAMLError:
                raise ValueError("config.yaml contient une erreur YAML.") from None
            _CONFIG = validate(migrate(raw))
        return _CONFIG


def reglage(chemin, defaut=None):
    conf = _charger()
    canonical = ALIASES.get(chemin, chemin)
    missing = object()
    value = _get(conf, canonical, missing)
    if value is missing:
        old = next((k for k, v in ALIASES.items() if v == canonical), canonical)
        value = _get(conf, old, defaut)
    return value


def revision():
    return _REVISION


def definir(chemin, valeur):
    return definir_plusieurs({chemin: valeur})


def definir_plusieurs(values):
    global _CONFIG, _REVISION
    with _LOCK:
        conf = migrate(_charger())
        for path, value in values.items():
            _set(conf, ALIASES.get(path, path), deepcopy(value))
        conf = validate(migrate(conf))
        FICHIER.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(
            prefix=".red-config-", suffix=".tmp", dir=FICHIER.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf8", newline="\n") as stream:
                yaml.safe_dump(conf, stream, allow_unicode=True, sort_keys=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, FICHIER)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        _CONFIG = conf
        _REVISION += 1


def save_migrated():
    definir_plusieurs({})
