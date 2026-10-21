# Ajouter un module à Red

Un module est une fonctionnalité. Un service est un moteur technique (STT, TTS,
LLM). Une intégration est un adaptateur externe. Un appareil est une entité
logique indépendante du protocole. Aucun compte ni transport réseau supplémentaire
n'est nécessaire pour utiliser ces contrats.

## Fichiers à créer

Copie `modules/demo/` dans `modules/mon_module/` et crée `__init__.py`,
`manifest.json`, `module.py`. Le manifeste doit porter le même ID que le dossier :

```json
{
  "id": "mon_module",
  "version": "1.0.0",
  "description": "Ma fonctionnalité locale",
  "entrypoint": "modules.mon_module.module:Module",
  "required_capabilities": ["events.local"],
  "optional_capabilities": ["home.devices"]
}
```

```python
from core.module import RedModule

class Module(RedModule):
    def register(self, app):
        self.app = app
        self.running = False
        self.message = app.config.get("message", "pong")
        app.register_tool(self.ping, name="mon_module_ping",
                          description="Teste ma fonctionnalité locale.")
        app.publish("mon_module.ping", self.ping)
        app.subscribe("mon_module.request", lambda event: self.ping())
        app.admin_endpoint("/health", self.health)

    def ping(self):
        return self.message

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def health(self):
        return {"ok": self.running}
```

Active ensuite le module dans `config.yaml` et redémarre Red :

```yaml
modules:
  mon_module:
    enabled: true
    message: "Bien reçu."
```

**Aucun fichier central à modifier** : ni registre, ni runtime, ni conversation,
ni panneau. La découverte lit d'abord les manifestes ; un module désactivé
n'importe pas son code. Le module de démonstration fourni reste désactivé par défaut.

## Contrat et cycle de vie

`DISCOVERED → REGISTERED → STARTED → STOPPED` ; `FAILED` signale un import,
une dépendance ou une initialisation impossible. Les capacités requises doivent
être disponibles avant l'import ; une capacité facultative se consulte par
`app.capabilities.get(name)`. `--check` retourne un échec si un module activé est
en panne. `runtime.modules.health()` donne les états sans lancer ses modèles.

Les ressources lourdes démarrent dans `start`, pas à l'import. Enregistre chaque
fermeture de watcher, connexion ou worker avec `app.on_stop(close)`. Les
abonnements, outils et capacités sont retirés automatiquement à l'arrêt. Un
endpoint déjà monté répond 503 quand son module est arrêté. Le chargement à chaud
de nouvelles routes n'est pas proposé : redémarre Red après changement de modules.

`register_tool` accepte les métadonnées du décorateur `@outil` existant :
`parametres`, `confirmation`, `lent`, `phrase_attente`, `annonce`, `mcp_expose`.
Un outil sensible utilise `permission_level="N2"` ; une action critique utilise
`permission_level="N3"`. Ces niveaux activent automatiquement la confirmation et
N3 interdit sa mémorisation. Aucune liste centrale à modifier pour un nouveau tool.
Le paramètre historique `confirmation=True` reste compatible (N2 par défaut).
Les outils critiques historiques restent N3, indépendamment des métadonnées.
La mémoire utilise toujours son service de proposition/validation ; ne contourne
jamais ce service par une écriture SQL directe.

Les routes `admin_endpoint` sont placées sous `/api/panneau/modules/<id>/...`,
protégées comme le reste du panneau et disponibles seulement quand il est activé.
Ne renvoie aucun secret ou contenu de mémoire protégée dans `health` ou les événements.
Les modules Python installés localement sont du code de confiance, pas des plugins sandboxés.

## Services, appareils, événements

`app.runtime.stt`, `.tts`, `.llm` chargent les services partagés paresseusement.
Les contrats portent un `AudioData` et un `ExecutionContext` ; ils n'ouvrent pas
le micro d'un satellite sur le serveur. Pour un appareil :

```python
devices = app.capabilities.require("home.devices")
devices.turn_on("salon.light")
```

L'intégration est résolue par le catalogue d'appareils. Le contexte possède
`source`, `session_id`, `room_id`, `device_id`, `satellite_id`, `user_id`.
`user_id` est une étiquette de routage, pas une preuve d'identité.
Utilise `Event.create(name, payload)` et le bus local ; garde le payload sérialisable.
Le transport MQTT/WebSocket et Home Assistant ne sont pas implémentés ici.
