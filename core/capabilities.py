"""Actions exécutables et contrats partagés, indépendants du transport."""

from dataclasses import dataclass, field
import copy
import inspect
import logging
from threading import RLock
from types import SimpleNamespace
from core.capability_errors import CapabilityExecutionError

LOG = logging.getLogger("assistant.capabilities")


@dataclass(frozen=True)
class CapabilityRequest:
    name: str
    arguments: dict = field(default_factory=dict)

    @property
    def outil(self):
        return self.name

    @property
    def type(self):
        return "outil"


@dataclass
class Capability:
    name: str
    tool: object
    owner: str
    aliases: tuple = ()
    intents: tuple = ()
    registry: object = field(default=None, repr=False)

    @property
    def description(self):
        return self.tool.description

    @property
    def arguments_schema(self):
        return copy.deepcopy(self.tool.parametres)

    @property
    def security_level(self):
        from security.authorization import niveau_outil
        return niveau_outil(self.tool)

    def _check_live(self):
        from core import registre
        if self.registry is not None:
            live = self.registry.resolve(self.name)
            if live is None or live.tool is not self.tool:
                raise CapabilityExecutionError("Cette capacité n'est plus disponible.")
        if registre.get(self.tool.nom) is not self.tool:
            raise CapabilityExecutionError("Cette action a été remplacée ou arrêtée.")

    def _invoke(self, **arguments):
        self._check_live()
        try:
            return self.tool.fonction(**arguments)
        except Exception as error:
            LOG.error("Capacité %s en échec (%s)", self.name, type(error).__name__)
            raise CapabilityExecutionError("Cette action n'a pas pu aboutir.") from None

    def execute(self, arguments=None):
        from security.authorization import execute
        self._check_live()
        arguments = copy.deepcopy({} if arguments is None else arguments)
        if not isinstance(arguments, dict):
            raise CapabilityExecutionError("Les arguments doivent former un objet.")
        try:
            inspect.signature(self.tool.fonction).bind(**arguments)
        except (ValueError, TypeError) as error:
            raise CapabilityExecutionError("Arguments invalides pour cette action.") from error
        # La confirmation conserve une fonction gardée, révoquée à l'arrêt.
        guarded = SimpleNamespace(**vars(self.tool))
        guarded.fonction = self._invoke
        return execute(guarded, arguments)

    def metadata(self):
        return {"name": self.name, "description": self.description,
                "owner": self.owner, "arguments": self.arguments_schema,
                "security_level": self.security_level, "aliases": list(self.aliases),
                "intents": list(self.intents)}


class CapabilityRegistry:
    def __init__(self):
        self._values = {}
        self._actions = {}
        self._aliases = {}
        self._routes = []
        self._selectors = []
        self._lock = RLock()
        self.legacy = None
        self.claimed_tool_modules = set()

    def publish(self, name, value, owner):
        if not name or not owner:
            raise ValueError("Capacité et propriétaire requis.")
        with self._lock:
            if name in self._values or name in self._actions or name in self._aliases:
                raise ValueError(f"Capacité déjà publiée : {name}")
            self._values[name] = (owner, value)

    def register(self, capability):
        names = (capability.name, *capability.aliases)
        if not capability.owner or len(set(names)) != len(names) or not all(names):
            raise ValueError("Nom, alias et propriétaire invalides.")
        with self._lock:
            if any(n in self._values or n in self._actions or n in self._aliases for n in names):
                raise ValueError("Capacité ou alias déjà publié.")
            capability.registry = self
            self._actions[capability.name] = capability
            self._aliases.update({n: capability.name for n in capability.aliases})
        return capability

    def resolve(self, name):
        with self._lock:
            action = self._actions.get(self._aliases.get(name, name))
            legacy = self.legacy
        return action or (legacy.resolve(name) if legacy else None)

    def execute(self, name, arguments=None):
        action = self.resolve(name)
        if action is None:
            raise CapabilityExecutionError(f"Capacité indisponible : {name}")
        return action.execute(arguments)

    def add_route(self, owner, handler, priority=100):
        with self._lock:
            self._routes.append((priority, owner, handler))
            self._routes.sort(key=lambda r: r[0])

    def add_selector(self, owner, selector):
        self._selectors.append((owner, selector))

    def select_domains(self, phrase):
        domains = set()
        for owner, selector in tuple(self._selectors):
            try:
                selected = selector(phrase)
                if selected is None:
                    return None
                domains.update(selected)
            except Exception:
                LOG.warning("Sélection des outils indisponible : %s", owner)
                return None
        return domains

    def route(self, phrase, context):
        for _, owner, handler in tuple(self._routes):
            try:
                request = handler(phrase, context)
                if request is not None and self.resolve(request.outil):
                    return request
            except Exception as error:
                LOG.warning("Route %s en échec (%s)", owner, type(error).__name__)
        return None

    def get(self, name, default=None):
        with self._lock:
            value = self._values.get(name)
        return value[1] if value else self.resolve(name) or default

    def require(self, name):
        value = self.get(name)
        if value is None:
            raise LookupError(f"Capacité absente : {name}")
        return value

    def remove_owner(self, owner):
        with self._lock:
            self._values = {k: v for k, v in self._values.items() if v[0] != owner}
            self._actions = {k: v for k, v in self._actions.items() if v.owner != owner}
            self._aliases = {k: v for k, v in self._aliases.items() if v in self._actions}
            self._routes = [r for r in self._routes if r[1] != owner]
            self._selectors = [r for r in self._selectors if r[0] != owner]
            if owner == "legacy_tools":
                self.legacy = None

    def actions(self, owner=None):
        with self._lock:
            actions = list(self._actions.values())
            legacy = self.legacy
        if legacy:
            actions.extend(c for c in legacy.all() if c.name not in self._actions and c.name not in self._aliases)
        return sorted((c for c in actions if owner is None or c.owner == owner), key=lambda c: c.name)

    def names(self):
        return sorted(set(self._values) | {c.name for c in self.actions()})
