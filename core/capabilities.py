"""Capacités nommées : contrat explicite, sans découverte ou connexion implicite."""

from threading import RLock


class CapabilityRegistry:
    def __init__(self):
        self._values = {}
        self._lock = RLock()

    def publish(self, name, value, owner):
        if not name or not owner:
            raise ValueError("Capacité et propriétaire requis.")
        with self._lock:
            if name in self._values:
                raise ValueError(f"Capacité déjà publiée : {name}")
            self._values[name] = (owner, value)

    def get(self, name, default=None):
        with self._lock:
            return self._values.get(name, (None, default))[1]

    def require(self, name):
        with self._lock:
            if name not in self._values:
                raise LookupError(f"Capacité absente : {name}")
            return self._values[name][1]

    def remove_owner(self, owner):
        with self._lock:
            self._values = {k: v for k, v in self._values.items() if v[0] != owner}

    def names(self):
        with self._lock:
            return sorted(self._values)
