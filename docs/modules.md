# Ajouter une fonctionnalité à Red

Un **module** expose des actions métier. Un **service** fournit STT, TTS ou LLM.
Une **intégration** adapte un système externe. Un **device** représente un appareil
indépendamment de Hue, Home Assistant ou MQTT. Aucun système multi-utilisateur
n'est ajouté par cette architecture.

## Trois fichiers et une configuration

Créer `modules/bonjour/__init__.py` (vide), `manifest.json` et `module.py`.
Le dossier et le champ `id` doivent correspondre :

```json
{
  "id": "bonjour",
  "name": "Salutations",
  "version": "1.0.0",
  "description": "Une première capacité locale",
  "entrypoint": "modules.bonjour.module:Module"
}
```

```python
from core.module import RedModule
from core.capabilities import CapabilityRequest

class Module(RedModule):
    def register(self, app):
        self.message = app.config.get("message", "Bonjour, Monsieur.")
        self.logger = app.logger
        app.capability(
            self.hello,
            name="bonjour.hello",
            description="Salue depuis le module Salutations.",
            arguments={"type": "object", "properties": {}},
            security_level="N1",
            intents=("bonjour module",),
        )
        app.route(self.route)

    def hello(self):
        return self.message

    def route(self, phrase, context):
        if phrase.lower().strip(" .!?") == "bonjour module":
            return CapabilityRequest("bonjour.hello")
```

Ajouter à la section existante de `config.yaml`, puis redémarrer Red :

```yaml
modules:
  bonjour:
    enabled: true
    message: "Bonjour, Monsieur."
```

Ne modifier ni le runtime, ni la conversation, ni le registre, ni le panneau.
Le module apparaît automatiquement dans **/panneau → Modules**. La version fournie
dans `modules/demo` expose `demo.hello`, répond à « bonjour module démo » et reste
désactivée par défaut. L'ancien `demo_ping` est conservé pour compatibilité.

## Exécution et sécurité

`registry.resolve("bonjour.hello")` retourne une capacité avec description,
propriétaire, schéma, alias, exemples d'intentions et niveau N1/N2/N3.
`registry.execute(name, arguments)` ou `capability.execute(arguments)` applique
la politique existante avant l'appel. Le modèle reçoit un nom d'outil compatible
avec les API, ici `bonjour_hello`, alias de la même capacité.

- N1 : exécution directe.
- N2 : confirmation, ou autorisation permanente déjà accordée en local.
- N3 : confirmation à chaque fois, y compris pour une commande vocale explicite.

`announcement=lambda args: "Je vais …"` personnalise l'annonce. Red ajoute
« Tu confirmes ? », sans énumérer les réponses possibles. Les alias passent par
la même permission. Une action proposée ne s'exécute qu'une fois ; arrêter son
module révoque l'exécution différée. Les restrictions du pont iPhone restent
appliquées par ce transport ; un satellite vocal garde sa confirmation de session.

`LegacyToolAdapter` expose les anciens outils sans réécrire leurs fonctions.
`app.adopt_tool(tool, name="domaine.action")` migre un outil en conservant son
identifiant de permission, son schéma et son annonce. Le manifeste déclare ses
anciens domaines dans `legacy_tool_modules` pour empêcher qu'une désactivation
soit contournée par l'adaptateur. Ne pas appeler directement `.tool.fonction` pour
orchestrer une action utilisateur : cela contournerait la politique d'exécution.

`app.register_tool` reste compatible et expose aussi une capacité. Pour la mémoire,
conserver le service de propositions et validations : aucune écriture SQL directe.
Les exemples `intents` décrivent les formulations ; `app.route` implémente leur
reconnaissance. Une route renvoie une demande, elle ne doit pas réaliser l'action.
Sa priorité numérique la plus basse est évaluée d'abord ; défaut 100.

## Cycle de vie et erreurs

Le manager découvre les manifests avant d'importer les modules activés. Les
champs facultatifs `required_capabilities` et `optional_capabilities` déclarent
des dépendances nommées. Les états publics du panneau sont ACTIVE, DISABLED,
ERROR, NOT_CONFIGURED et STOPPED ; les anciens états internes sont conservés.

Implémenter `start`, `stop`, `health` au besoin. Un `health` retourne au minimum
`{"ok": True}` et peut ajouter un `detail` sans secrets. La santé indique celle
du module chargé, pas la disponibilité garantie de chaque service distant.
Lever `ModuleConfigurationError` si une configuration indispensable manque.
Un manifeste, un import ou une action défectueux n'arrête pas les autres modules.

Enregistrer chaque fermeture avec `app.on_stop(close)`. Les outils créés par le
module, les capacités, les routes et les abonnements sont retirés à l'arrêt ; un
endpoint administratif encore monté retourne 503. Pas de rechargement à chaud :
modifier l'activation dans le YAML puis redémarrer Red.

`app.config` est une copie de la configuration du module. `app.settings.reglage`
donne accès aux paramètres partagés existants. `app.logger` utilise le journal
central. Ne journaliser ni secrets, ni contenu de mémoire protégée, ni transcription.
Le code Python des modules est du code local de confiance, pas un plugin sandboxé.

## Contrats techniques et espace

`app.publish` conserve le rôle distinct de publication d'un service ou objet partagé.
`app.capabilities.require("home.devices").turn_on("salon.light")` utilise le
catalogue d'appareils sans dépendre du protocole. STT/TTS/LLM sont accessibles
paresseusement via `app.runtime.stt`, `.tts`, `.llm`.

Le contexte d'une route contient `source`, `session_id`, `room_id`, `device_id`,
`satellite_id`, `user_id`. Le dernier est une étiquette de contexte historique,
pas une authentification. Les événements `Event.create(name, payload)` portent
ce contexte, un horodatage et un payload JSON ; aucune fonction Python ne doit
être insérée dans ce payload. `app.subscribe` détache automatiquement les abonnements.

L'entrée locale publie le contrat facultatif `audio.local` puis l'événement
`audio.ready`. Le module de compatibilité s'y branche pour les anciens hooks
microphone ; les autres transports n'ont pas à posséder cette entrée audio.
Home Assistant/MQTT et de nouveaux satellites ne sont pas implémentés ici.

## Modules déjà migrés

| Module | Capacités principales |
|---|---|
| computer | `computer.execute_action` (alias `controle_pc_astra`, N3) |
| vision | `vision.analyze_screen`, `vision.capture_screen` |
| hermes | `hermes.delegate`, `hermes.tasks`, `hermes.create_content` |
| legacy_tools | Ancien catalogue et heuristiques, initialisations locales |
| demo | `demo.hello` et ancien test `demo_ping` |

Les quatre premiers sont activés par défaut lors de la migration de configuration,
sauf désactivation explicite existante. Astra conserve ses besoins OpenAI ; la
vision explique son indisponibilité en mode local ; Hermes conserve son moteur
CLI/HTTP configuré. La refonte n'ajoute aucune dépendance Python lourde.
